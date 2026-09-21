import test from "node:test";
import assert from "node:assert/strict";
import { buildGreetingContext } from "./greetingContext.js";
import {
  DEFAULT_GREETING_COPY,
  HERO_STATUS,
  resolveGreeting,
  resolveGreetingModel,
} from "./greetingResolver.js";

const wib = (hour, minute = 0) => new Date(Date.UTC(2026, 8, 21, hour - 7, minute));

const SETTINGS = { display_name: "Lingga", timezone: "Asia/Jakarta", language: "id" };
const model = (hour, extra = {}) =>
  resolveGreetingModel({ settings: SETTINGS, now: wib(hour), ...extra });

// ============================================================
// HEADLINE PER PERIODE (contoh persis dari spesifikasi)
// ============================================================

test("morning: 'Selamat pagi, Lingga'", () => {
  const hero = model(8);
  assert.equal(hero.greeting, "Selamat pagi, Lingga");
  assert.equal(hero.time_period, "morning");
});

test("afternoon: 'Selamat siang, Lingga'", () => {
  const hero = model(13);
  assert.equal(hero.greeting, "Selamat siang, Lingga");
  assert.equal(hero.time_period, "afternoon");
});

test("evening: 'Selamat malam, Lingga'", () => {
  const hero = model(19);
  assert.equal(hero.greeting, "Selamat malam, Lingga");
  assert.equal(hero.time_period, "evening");
});

test("night: 'Masih semangat ngoding, Lingga?'", () => {
  for (const hour of [23, 0, 2]) {
    const hero = model(hour);
    assert.equal(hero.greeting, "Masih semangat ngoding, Lingga?", `jam ${hour}`);
    assert.equal(hero.time_period, "night");
  }
});

test("timezone terkonfigurasi menentukan headline (bukan timezone mesin)", () => {
  const now = new Date("2026-09-21T01:00:00Z");
  const greet = (timezone) => resolveGreetingModel({ settings: { ...SETTINGS, timezone }, now }).greeting;

  assert.equal(greet("Asia/Jakarta"), "Selamat pagi, Lingga");
  assert.equal(greet("America/New_York"), "Selamat malam, Lingga");
  assert.equal(greet("Pacific/Auckland"), "Selamat siang, Lingga");
});

// ============================================================
// NAMA
// ============================================================

test("tanpa nama: tidak ada koma/tanda tanya menggantung", () => {
  const noName = (hour) => resolveGreetingModel({ now: wib(hour) }).greeting;

  assert.equal(noName(8), "Selamat pagi");
  assert.equal(noName(13), "Selamat siang");
  assert.equal(noName(19), "Selamat malam");
  assert.equal(noName(23), "Masih semangat ngoding?");
});

test("nickname didahulukan dari display_name; fallback ke display_name lalu persona.user_name", () => {
  const greet = (settings, persona) => resolveGreetingModel({ settings, persona, now: wib(8) }).greeting;

  assert.equal(greet({ display_name: "Lingga Pratama", nickname: "Ling" }), "Selamat pagi, Ling");
  assert.equal(greet({ display_name: "Lingga Pratama" }), "Selamat pagi, Lingga Pratama");
  assert.equal(greet(null, { user_name: "Lingga" }), "Selamat pagi, Lingga");
});

test("nama yang memuat placeholder/pola pengganti tidak diperluas", () => {
  const greeting = resolveGreetingModel({
    settings: { display_name: "{name} $& {count}" },
    now: wib(8),
  }).greeting;

  assert.equal(greeting, "Selamat pagi, {name} $& {count}");
});

// ============================================================
// BAHASA & COPY KONFIGURABEL
// ============================================================

test("language en / id-ID / tidak dikenal", () => {
  const greet = (language) => resolveGreetingModel({ settings: { ...SETTINGS, language }, now: wib(8) }).greeting;

  assert.equal(greet("en"), "Good morning, Lingga");
  assert.equal(greet("id-ID"), "Selamat pagi, Lingga");
  assert.equal(greet("fr"), "Selamat pagi, Lingga"); // tidak ada copy fr -> id
});

test("copy kustom menimpa sebagian; sisanya tetap default", () => {
  const copy = { id: { greeting: { morning: { named: "Pagi cerah, {name}!", anonymous: "Pagi cerah!" } } } };

  assert.equal(model(8, { copy }).greeting, "Pagi cerah, Lingga!");
  assert.equal(model(13, { copy }).greeting, "Selamat siang, Lingga"); // tidak ditimpa
  assert.equal(resolveGreetingModel({ copy, now: wib(8) }).greeting, "Pagi cerah!");
});

test("copy kustom rusak diabaikan (jatuh ke default), tidak raise", () => {
  for (const copy of [null, "x", 5, { id: null }, { id: { greeting: { morning: { anonymous: "" } } } }]) {
    assert.equal(model(8, { copy }).greeting, "Selamat pagi, Lingga");
  }
});

test("periode kustom tanpa copy -> headline generik, bukan error", () => {
  const context = { ...buildGreetingContext({ settings: SETTINGS }), time_period: "late_afternoon" };

  assert.equal(resolveGreeting(context).greeting, "Halo, Lingga");

  const copy = { id: { greeting: { late_afternoon: { named: "Selamat sore, {name}", anonymous: "Selamat sore" } } } };
  assert.equal(resolveGreeting(context, { copy }).greeting, "Selamat sore, Lingga");
});

test("default copy tidak bisa dimutasi", () => {
  assert.throws(() => {
    "use strict";
    DEFAULT_GREETING_COPY.id.greeting.morning.named = "diubah";
  }, TypeError);
});

// ============================================================
// STATE-AWARE
// ============================================================

test("connection count aktif -> subtitle menyebut jumlah, status connected", () => {
  const hero = model(8, { connections: 2 });

  assert.equal(hero.status, HERO_STATUS.CONNECTED);
  assert.equal(hero.subtitle, "2 koneksi perangkat aktif.");
  assert.equal(hero.greeting, "Selamat pagi, Lingga"); // headline tidak berubah oleh state
});

test("connections berupa array dihitung dari panjangnya", () => {
  assert.equal(model(8, { connections: [{}, {}, {}] }).subtitle, "3 koneksi perangkat aktif.");
});

test("connection count 0 / tidak valid tidak dianggap koneksi aktif", () => {
  for (const connections of [0, -1, Number.NaN, "3", undefined]) {
    assert.notEqual(model(8, { connections }).status, HERO_STATUS.CONNECTED);
  }
});

test("activity_state null: tidak raise, tidak memengaruhi status", () => {
  const hero = model(8, { activity: null });

  assert.equal(hero.status, HERO_STATUS.IDLE);
  assert.equal(typeof hero.greeting, "string");

  const withConnection = model(8, { activity: null, connections: 1 });
  assert.equal(withConnection.status, HERO_STATUS.CONNECTED);
});

test("activity network_work mengalahkan koneksi & workspace", () => {
  const hero = model(8, { activity: "network_work", connections: 3, workspace: true });

  assert.equal(hero.status, HERO_STATUS.NETWORK_WORK);
  assert.equal(hero.subtitle, "Ada pekerjaan jaringan yang sedang berjalan.");
});

test("workspace aktif / tidak ada workspace / tidak diketahui", () => {
  assert.deepEqual(
    [model(8, { workspace: true }).status, model(8, { workspace: true }).subtitle],
    [HERO_STATUS.WORKSPACE_ACTIVE, "Workspace sedang aktif."]
  );
  assert.deepEqual(
    [model(8, { workspace: false }).status, model(8, { workspace: false }).subtitle],
    [HERO_STATUS.NO_WORKSPACE, "Belum ada workspace aktif."]
  );
  assert.equal(model(8, { workspace: undefined }).status, HERO_STATUS.IDLE);
});

test("prioritas: koneksi mengalahkan workspace; activity 'idle' tidak menutupi state lain", () => {
  assert.equal(model(8, { connections: 1, workspace: false }).status, HERO_STATUS.CONNECTED);
  assert.equal(model(8, { activity: "idle", workspace: true }).status, HERO_STATUS.WORKSPACE_ACTIVE);
});

test("idle: subtitle dari daftar varian, deterministik per seed", () => {
  const lines = DEFAULT_GREETING_COPY.id.idle;
  const context = buildGreetingContext({ settings: SETTINGS, now: wib(8) });

  const picked = [0, 1, 2, 3, 4, 5].map((seed) => resolveGreeting(context, { seed }).subtitle);

  assert.deepEqual(picked, [...lines, ...lines]);
  assert.equal(resolveGreeting(context, { seed: 4 }).subtitle, resolveGreeting(context, { seed: 4 }).subtitle);
  assert.equal(resolveGreeting(context, { seed: -1 }).subtitle, lines[1]);
  assert.equal(resolveGreeting(context, { seed: "x" }).subtitle, lines[0]);
});

test("varian idle stabil dalam jam yang sama, boleh berganti antar jam", () => {
  const a = resolveGreetingModel({ settings: SETTINGS, now: wib(8, 5) });
  const b = resolveGreetingModel({ settings: SETTINGS, now: wib(8, 55) });
  const c = resolveGreetingModel({ settings: SETTINGS, now: wib(9, 5) });

  assert.equal(a.subtitle, b.subtitle);
  assert.ok(DEFAULT_GREETING_COPY.id.idle.includes(c.subtitle));
});

// ============================================================
// FALLBACK: settings tidak ada / error tak terduga
// ============================================================

test("settings tidak tersedia: tetap menyapa dari persona, fallback=false (bukan error)", () => {
  const persona = { user_name: "Lingga", timezone: "Asia/Jakarta", language: "id" };

  for (const settings of [undefined, null, () => null, () => { throw new Error("belum siap"); }]) {
    const hero = resolveGreetingModel({ settings, persona, now: wib(8) });

    assert.equal(hero.greeting, "Selamat pagi, Lingga");
    assert.equal(hero.fallback, false);
  }
});

test("tanpa input sama sekali: tidak raise, tetap ada greeting", () => {
  for (const input of [undefined, null, {}, "x", 5]) {
    const hero = resolveGreetingModel(input);

    assert.equal(typeof hero.greeting, "string");
    assert.ok(hero.greeting.length > 0);
    assert.equal(hero.fallback, false);
  }
});

test("error tak terduga di layer baru -> greeting.js lama (fallback=true), nama tetap terbawa", () => {
  const hero = resolveGreetingModel({
    persona: { user_name: "Lingga", timezone: "Asia/Jakarta" },
    now: wib(8),
    get copy() {
      throw new Error("copy rusak");
    },
  });

  assert.equal(hero.fallback, true);
  assert.equal(hero.subtitle, null);
  assert.equal(hero.time_period, null);
  assert.match(hero.greeting, /Lingga/);
});

test("greeting lama pun tidak bisa jalan -> teks statis, tetap tidak raise", () => {
  const hero = resolveGreetingModel({
    get persona() {
      throw new Error("persona rusak");
    },
  });

  assert.equal(hero.fallback, true);
  assert.equal(hero.greeting, "Halo! Ada yang bisa dibantu?");
});

test("resolveGreeting toleran terhadap context parsial/rusak", () => {
  for (const context of [undefined, null, {}, "x", { time_period: 5, connection_count: "banyak" }]) {
    const hero = resolveGreeting(context);

    assert.equal(hero.greeting, "Halo");
    assert.equal(hero.status, HERO_STATUS.IDLE);
  }
});

// ============================================================
// SIFAT: deterministik, murah, tanpa LLM/jaringan
// ============================================================

test("deterministik: input sama -> Hero Model sama", () => {
  const input = { settings: SETTINGS, workspace: true, connections: 2, activity: null, now: wib(19) };

  assert.deepEqual(resolveGreetingModel(input), resolveGreetingModel(input));
});

test("tidak memanggil fetch/jaringan sama sekali", () => {
  const originalFetch = globalThis.fetch;
  let calls = 0;

  globalThis.fetch = () => {
    calls += 1;
    throw new Error("fetch tidak boleh dipanggil oleh layer greeting");
  };

  try {
    resolveGreetingModel({ settings: SETTINGS, connections: 1, now: wib(8) });
    resolveGreetingModel({ now: wib(23) });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(calls, 0);
});

test("resolusi murah: 10.000 panggilan selesai jauh di bawah 1 detik", () => {
  const start = performance.now();

  for (let i = 0; i < 10_000; i += 1) {
    resolveGreetingModel({ settings: SETTINGS, connections: i % 4, now: wib(i % 24) });
  }

  assert.ok(performance.now() - start < 1000);
});
