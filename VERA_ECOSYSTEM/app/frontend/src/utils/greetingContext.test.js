import test from "node:test";
import assert from "node:assert/strict";
import {
  ACTIVITY_STATE,
  DEFAULT_GREETING_SETTINGS,
  TIME_PERIOD,
  WORKSPACE_STATE,
  buildGreetingContext,
  isValidTimeZone,
  normalizeConnectionCount,
  resolveHourInTimezone,
  resolveTimePeriod,
} from "./greetingContext.js";

// Asia/Jakarta = UTC+7 tanpa DST. jam WIB h:m -> instant UTC tetap (21 Sep 2026).
const wib = (hour, minute = 0) => new Date(Date.UTC(2026, 8, 21, hour - 7, minute));
const periodAt = (hour, minute = 0, extra = {}) =>
  buildGreetingContext({ persona: { timezone: "Asia/Jakarta" }, now: wib(hour, minute), ...extra }).time_period;

const { MORNING, AFTERNOON, EVENING, NIGHT } = TIME_PERIOD;

// ============================================================
// PERIODE
// ============================================================

test("morning / afternoon / evening / night pada jam representatif", () => {
  assert.equal(periodAt(8), MORNING);
  assert.equal(periodAt(13), AFTERNOON);
  assert.equal(periodAt(19), EVENING);
  assert.equal(periodAt(23), NIGHT);
});

test("batas periode tepat (menit terakhir vs menit pertama)", () => {
  const table = [
    [0, 0, NIGHT], [3, 59, NIGHT],
    [4, 0, MORNING], [10, 59, MORNING],
    [11, 0, AFTERNOON], [17, 59, AFTERNOON],
    [18, 0, EVENING], [21, 59, EVENING],
    [22, 0, NIGHT], [23, 59, NIGHT],
  ];

  for (const [h, m, expected] of table) {
    assert.equal(periodAt(h, m), expected, `${h}:${String(m).padStart(2, "0")}`);
  }
});

test("tengah malam = jam 0 (bukan 24) dan dini hari tetap night", () => {
  assert.equal(resolveHourInTimezone("Asia/Jakarta", wib(0, 0)), 0);
  assert.equal(resolveHourInTimezone("Asia/Jakarta", wib(0, 30)), 0);
  assert.equal(periodAt(0), NIGHT);
  assert.equal(periodAt(2), NIGHT);
});

test("boundaries kustom (data, bukan logika) dan boundaries rusak jatuh ke default", () => {
  const custom = [
    { from: 0, period: "night" },
    { from: 5, period: "morning" },
    { from: 15, period: "late_afternoon" },
  ];

  assert.equal(periodAt(16, 0, { boundaries: custom }), "late_afternoon");
  assert.equal(periodAt(8, 0, { boundaries: custom }), MORNING);

  for (const broken of [null, [], "x", [{ from: "a", period: "x" }], [{ from: 30, period: "x" }]]) {
    assert.equal(periodAt(8, 0, { boundaries: broken }), MORNING);
  }

  // jam sebelum entri pertama = lanjutan periode terakhir hari sebelumnya
  assert.equal(resolveTimePeriod(2, [{ from: 5, period: "morning" }, { from: 20, period: "night" }]), "night");
  assert.equal(resolveTimePeriod(Number.NaN), NIGHT);
});

// ============================================================
// TIMEZONE
// ============================================================

test("timezone terkonfigurasi menentukan periode: instant yang sama, periode beda", () => {
  const instant = new Date("2026-09-21T01:00:00Z"); // 08:00 WIB, 21:00 New York (EDT), 13:00 Auckland (NZST)
  const at = (timezone) => buildGreetingContext({ settings: { timezone }, now: instant });

  assert.equal(at("Asia/Jakarta").time_period, MORNING);
  assert.equal(at("America/New_York").time_period, EVENING);
  assert.equal(at("Pacific/Auckland").time_period, AFTERNOON);
  assert.equal(at("America/New_York").timezone, "America/New_York");
});

test("timezone server/mesin TIDAK dipakai: hasil sama walau TZ proses berubah", (t) => {
  const instant = wib(8);
  const original = process.env.TZ;
  const before = instant.getHours();

  try {
    process.env.TZ = "Pacific/Kiritimati"; // UTC+14
    if (instant.getHours() === before) {
      t.skip("runtime tidak mengizinkan mengganti TZ proses");
      return;
    }

    assert.equal(buildGreetingContext({ persona: { timezone: "Asia/Jakarta" }, now: instant }).time_period, MORNING);
  } finally {
    if (original === undefined) delete process.env.TZ;
    else process.env.TZ = original;
  }
});

test("timezone tidak valid: coba kandidat berikutnya (settings -> persona -> default)", () => {
  const now = wib(8);

  const fromPersona = buildGreetingContext({
    settings: { timezone: "Bukan/Zona" },
    persona: { timezone: "Asia/Tokyo" },
    now,
  });
  assert.equal(fromPersona.timezone, "Asia/Tokyo");

  const fromDefault = buildGreetingContext({
    settings: { timezone: "Bukan/Zona" },
    persona: { timezone: 123 },
    now,
  });
  assert.equal(fromDefault.timezone, DEFAULT_GREETING_SETTINGS.timezone);
  assert.equal(fromDefault.time_period, MORNING);

  assert.equal(isValidTimeZone("Asia/Jakarta"), true);
  assert.equal(isValidTimeZone("Bukan/Zona"), false);
  assert.equal(isValidTimeZone("   "), false);
  assert.equal(isValidTimeZone(undefined), false);
});

test("timezone di settings menang atas persona", () => {
  const context = buildGreetingContext({
    settings: { timezone: "Asia/Tokyo" },
    persona: { timezone: "Asia/Jakarta" },
    now: wib(8),
  });

  assert.equal(context.timezone, "Asia/Tokyo");
  assert.equal(context.time_period, MORNING); // 10:00 JST
});

test("now tidak valid dipakai sebagai 'sekarang' tanpa raise", () => {
  for (const now of [undefined, null, "kemarin", Number.NaN, new Date("x")]) {
    assert.doesNotThrow(() => buildGreetingContext({ now }));
  }
});

// ============================================================
// NAMA
// ============================================================

test("display name hilang -> null (bukan 'undefined'/kosong)", () => {
  const context = buildGreetingContext({ now: wib(8) });

  assert.equal(context.display_name, null);
  assert.equal(context.nickname, null);
});

test("nama kosong / spasi / bukan string dianggap tidak ada; nama di-trim", () => {
  assert.equal(buildGreetingContext({ settings: { display_name: "   " } }).display_name, null);
  assert.equal(buildGreetingContext({ settings: { display_name: 42 } }).display_name, null);
  assert.equal(buildGreetingContext({ settings: { display_name: "  Lingga " } }).display_name, "Lingga");
});

test("display_name: settings > persona.user_name; nickname hanya dari settings", () => {
  const both = buildGreetingContext({
    settings: { display_name: "Lingga Pratama", nickname: "Lingga" },
    persona: { user_name: "Nama Lama" },
  });
  assert.equal(both.display_name, "Lingga Pratama");
  assert.equal(both.nickname, "Lingga");

  const personaOnly = buildGreetingContext({ persona: { user_name: "Lingga" } });
  assert.equal(personaOnly.display_name, "Lingga");
  assert.equal(personaOnly.nickname, null);
});

test("assistant_name & language: settings > persona > default; language dinormalisasi", () => {
  assert.equal(buildGreetingContext({}).assistant_name, "AIRA");
  assert.equal(buildGreetingContext({}).language, "id");

  const context = buildGreetingContext({
    settings: { assistant_name: "Akane", language: "EN-us" },
    persona: { assistant_name: "AIRA", language: "id" },
  });
  assert.equal(context.assistant_name, "Akane");
  assert.equal(context.language, "en");

  assert.equal(buildGreetingContext({ persona: { language: "id_ID" } }).language, "id");
});

// ============================================================
// SETTINGS TIDAK TERSEDIA
// ============================================================

test("settings tidak tersedia (berbagai bentuk) -> context tetap terbentuk dari persona/default", () => {
  const persona = { user_name: "Lingga", timezone: "Asia/Jakarta", language: "id", assistant_name: "AIRA" };
  const unavailable = [
    undefined,
    null,
    "bukan objek",
    42,
    () => null,
    () => undefined,
    () => {
      throw new Error("Settings Service belum siap");
    },
    Promise.resolve({ display_name: "Tidak boleh terpakai" }),
    () => Promise.resolve({ display_name: "Tidak boleh terpakai" }),
  ];

  for (const settings of unavailable) {
    const context = buildGreetingContext({ settings, persona, now: wib(8) });

    assert.equal(context.display_name, "Lingga");
    assert.equal(context.timezone, "Asia/Jakarta");
    assert.equal(context.time_period, MORNING);
  }
});

test("settings & persona sama-sama tidak ada -> default penuh, tidak raise", () => {
  const context = buildGreetingContext({ settings: null, persona: null, now: wib(13) });

  assert.deepEqual(
    { ...context },
    {
      display_name: null,
      nickname: null,
      assistant_name: "AIRA",
      timezone: "Asia/Jakarta",
      language: "id",
      time_period: AFTERNOON,
      workspace_state: null,
      connection_count: 0,
      activity_state: null,
    }
  );

  assert.doesNotThrow(() => buildGreetingContext());
  assert.doesNotThrow(() => buildGreetingContext(undefined));
});

test("settings sebagai fungsi sinkron dibaca sekali dan dipakai", () => {
  let calls = 0;
  const context = buildGreetingContext({
    settings: () => {
      calls += 1;
      return { display_name: "Lingga", timezone: "Asia/Tokyo" };
    },
    now: wib(8),
  });

  assert.equal(calls, 1);
  assert.equal(context.display_name, "Lingga");
  assert.equal(context.timezone, "Asia/Tokyo");
});

// ============================================================
// STATE: workspace / koneksi / activity
// ============================================================

test("connection_count: angka, array, dan nilai tidak valid", () => {
  const count = (connections) => buildGreetingContext({ connections }).connection_count;

  assert.equal(count(3), 3);
  assert.equal(count(2.9), 2);
  assert.equal(count([{ id: "a" }, { id: "b" }]), 2);
  assert.equal(count([]), 0);
  assert.equal(count(0), 0);

  for (const bad of [-5, Number.NaN, Infinity, "3", true, null, undefined, {}]) {
    assert.equal(count(bad), 0, String(bad));
  }

  assert.equal(normalizeConnectionCount(7), 7);
});

test("activity_state null/undefined/tidak dikenal -> null; nilai dikenal dipertahankan", () => {
  const state = (activity) => buildGreetingContext({ activity }).activity_state;

  assert.equal(state(null), null);
  assert.equal(state(undefined), null);
  assert.equal(state("THINKING"), null); // state milik Thinking/Streaming: bukan urusan layer ini
  assert.equal(state(42), null);

  assert.equal(state("idle"), ACTIVITY_STATE.IDLE);
  assert.equal(state("NETWORK_WORK"), ACTIVITY_STATE.NETWORK_WORK);
});

test("workspace_state: boolean, string, {active}, dan tidak diketahui", () => {
  const state = (workspace) => buildGreetingContext({ workspace }).workspace_state;

  assert.equal(state(true), WORKSPACE_STATE.ACTIVE);
  assert.equal(state("active"), WORKSPACE_STATE.ACTIVE);
  assert.equal(state({ active: true, path: "Projects" }), WORKSPACE_STATE.ACTIVE);

  assert.equal(state(false), WORKSPACE_STATE.NONE);
  assert.equal(state("none"), WORKSPACE_STATE.NONE);
  assert.equal(state({ active: false }), WORKSPACE_STATE.NONE);

  for (const unknown of [undefined, null, "entah", 1, {}]) {
    assert.equal(state(unknown), null, String(unknown));
  }
});

// ============================================================
// BENTUK & DETERMINISME
// ============================================================

test("GreetingContext: tepat 9 field sesuai spesifikasi, beku", () => {
  const context = buildGreetingContext({ now: wib(8) });

  assert.deepEqual(Object.keys(context).sort(), [
    "activity_state",
    "assistant_name",
    "connection_count",
    "display_name",
    "language",
    "nickname",
    "time_period",
    "timezone",
    "workspace_state",
  ]);
  assert.equal(Object.isFrozen(context), true);
});

test("deterministik: input sama -> context sama; input tidak dimutasi", () => {
  const input = {
    settings: Object.freeze({ display_name: "Lingga", timezone: "Asia/Jakarta" }),
    persona: Object.freeze({ language: "id" }),
    workspace: true,
    connections: 2,
    activity: "idle",
    now: wib(19),
  };

  assert.deepEqual(buildGreetingContext(input), buildGreetingContext(input));
});
