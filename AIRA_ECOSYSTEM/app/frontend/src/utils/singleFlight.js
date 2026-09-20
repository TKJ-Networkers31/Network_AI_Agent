/**
 * createSingleFlight — membungkus fungsi async supaya panggilan yang
 * datang saat eksekusi sebelumnya masih berjalan MEMAKAI promise yang sama
 * (tidak menjalankan task lagi). Setelah selesai (sukses/gagal), panggilan
 * berikutnya menjalankan task baru. Dipakai untuk mencegah pembuatan sesi ganda.
 */
export function createSingleFlight(task) {
  let inflight = null;

  return function run(...args) {
    if (!inflight) {
      inflight = (async () => task(...args))().finally(() => {
        inflight = null;
      });
    }
    return inflight;
  };
}