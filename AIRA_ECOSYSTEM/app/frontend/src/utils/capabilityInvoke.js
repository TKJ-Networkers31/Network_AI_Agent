// src/utils/capabilityInvoke.js
//
// SPRINT 2.7 - W8 (Dynamic Capability UI)
//
// Dispatcher generik: menjalankan efek UI sesuai `capability.action.type`
// yang dikirim backend. File ini TIDAK mendefinisikan kapabilitas apa pun -
// hanya tahu cara mengeksekusi beberapa "tipe aksi" umum yang sudah ada di
// AIRA (kirim pesan ke chat, jalankan tool lewat slash command, buka
// tautan, operasi workspace lewat api.workspace.*). Backend tetap sumber
// kebenaran soal kapabilitas mana yang ada dan kapan aktif; frontend hanya
// tahu cara "menjalankan" beberapa bentuk aksi generik.
//
// helpers:
//   onSend(text)          - kirim pesan chat (dari useChatRuntime().sendMessage
//                            lewat ChatPage, atau helper sejenis)
//   notify({type,message})- toast (dari useToast())
//   onWorkspaceChange()   - dipanggil setelah operasi workspace berhasil,
//                            supaya pemanggil bisa refresh daftar file-nya

import { api } from "../api.js";

export async function invokeCapability(capability, helpers = {}) {
  const { onSend, notify, onWorkspaceChange } = helpers;
  const action = capability?.action || {};

  try {
    switch (action.type) {
      case "prompt": {
        if (!action.prompt) throw new Error("Kapabilitas ini tidak menyertakan prompt.");
        if (!onSend) throw new Error("Tidak ada saluran chat untuk menjalankan kapabilitas ini.");
        await onSend(action.prompt);
        return true;
      }

      case "tool": {
        if (!action.tool) throw new Error("Kapabilitas ini tidak menyertakan nama tool.");
        if (!onSend) throw new Error("Tidak ada saluran chat untuk menjalankan kapabilitas ini.");
        await onSend(`/${action.tool} ${action.args || ""}`.trim());
        return true;
      }

      case "navigate": {
        if (!action.href) throw new Error("Kapabilitas ini tidak menyertakan tautan.");
        window.open(action.href, "_blank", "noopener,noreferrer");
        return true;
      }

      case "workspace": {
        await runWorkspaceAction(action);
        onWorkspaceChange?.();
        return true;
      }

      default:
        throw new Error(`Tipe aksi "${action.type || "tidak diketahui"}" belum didukung di UI ini.`);
    }
  } catch (err) {
    notify?.({ type: "error", message: err.message || "Kapabilitas gagal dijalankan." });
    return false;
  }
}

async function runWorkspaceAction(action) {
  switch (action.workspace_op) {
    case "delete":
      return api.workspace.delete(action.file_path);
    case "restore":
      return api.workspace.restore(action.payload?.trash_id);
    case "move":
      return api.workspace.move(action.file_path, action.payload?.destination);
    case "copy":
      return api.workspace.copy(action.file_path, action.payload?.destination);
    case "mkdir":
      return api.workspace.mkdir(action.payload?.path);
    default:
      throw new Error("Operasi workspace tidak dikenal.");
  }
}
