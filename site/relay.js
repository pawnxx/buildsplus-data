"use strict";

const parameters = new URLSearchParams(location.search);
const sort = parameters.get("sort");
const language = parameters.get("lang");
const hero = parameters.get("hero");
const sorts = ["default", "rank", "date"];
const sortKey = "personal-builds-sort-v1";
const languageKey = "personal-builds-language-v1";
let frame = 0;

function waitForAcknowledgement() {
    return new Promise((resolve, reject) => {
        function acknowledged() {
            clearTimeout(timeout);
            resolve();
        }
        const timeout = setTimeout(() => {
            removeEventListener("hashchange", acknowledged);
            reject(new Error("Panorama did not acknowledge this frame"));
        }, 6000);
        addEventListener("hashchange", acknowledged, { once: true });
    });
}

async function send(packet) {
    try {
        const saved = localStorage.getItem(languageKey);
        if (saved === "ru" || saved === "en") packet = { ...packet, language: saved };
    } catch {}
    const id = ++frame;
    const data = encodeURIComponent(JSON.stringify(packet));
    if (data.length > 190000) throw new Error("Snapshot is too large");
    for (let offset = 0; offset < data.length; offset += 3072) {
        const chunk = data.slice(offset, offset + 3072);
        const ack = waitForAcknowledgement();
        document.title = "modlock:snapshot:" + JSON.stringify({ id, offset, total: data.length, chunk });
        await ack;
    }
}

function readSort() {
    try {
        const saved = localStorage.getItem(sortKey);
        if (sorts.includes(saved)) return saved;
    } catch {}
    return "default";
}

async function serve() {
    if ((language === "ru" || language === "en") && hero === null && sort === null) {
        localStorage.setItem(languageKey, language);
        await send({ kind: "personal-builds-language", language });
        return;
    }
    if (language !== null) return;
    if (sorts.includes(sort) && hero === null) {
        localStorage.setItem(sortKey, sort);
        await send({ kind: "personal-builds-sort", sort });
        return;
    }
    if (sort !== null || !/^[1-9]\d{0,3}$/.test(hero)) return;
    const empty = { kind: "personal-builds-v1", hero: { id: Number(hero) }, phase: "offline" };
    async function receive() {
        try {
            const response = await fetch("data/" + hero + ".json", { cache: "no-store", credentials: "omit" });
            if (response.ok) {
                const packet = await response.json();
                if (packet.kind === empty.kind && packet.hero?.id === empty.hero.id) return packet;
            }
        } catch {}
        return null;
    }
    let packet = await receive();
    if (!packet) { await send({ ...empty, sort: readSort() }); return; }
    if (packet.phase === "offline") { await send({ ...packet, sort: readSort() }); return; }
    if (packet.verification?.total > 0 && packet.verification.checked === packet.verification.total) {
        await send({ ...packet, phase: "live", sort: readSort() });
        return;
    }
    function signature(value) {
        return JSON.stringify([value.hero, value.authorRanks, value.authorRankDetails,
            value.rankSeason, value.previousEternus, value.patchAt]);
    }
    const deadline = Date.now() + 11000;
    let previous = signature(packet);
    await send({ ...packet, phase: "cached", sort: readSort() });
    while (Date.now() + 2300 < deadline) {
        await new Promise(resolve => setTimeout(resolve, 2200));
        const latest = await receive();
        if (!latest) continue;
        packet = latest;
        if (packet.phase === "offline") break;
        const current = signature(packet);
        if (current !== previous) {
            previous = current;
            await send({ ...packet, phase: "cached", sort: readSort() });
        }
        if (packet.verification?.total > 0 && packet.verification.checked === packet.verification.total) break;
    }
    await send({ ...packet, phase: packet.phase === "offline" ? "offline" : "live", sort: readSort() });
}

serve().catch(() => { document.title = "Personal Builds unavailable"; });
