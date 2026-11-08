// src/utils/leaflet.js
// Satu pintu import Leaflet: memperbaiki ikon marker default di Vite
// + konstanta tile OpenStreetMap yang dipakai MapBlock & LocationPinPicker.
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import icon2x from "leaflet/dist/images/marker-icon-2x.png";
import icon from "leaflet/dist/images/marker-icon.png";
import shadow from "leaflet/dist/images/marker-shadow.png";

delete L.Icon.Default.prototype._getIconUrl;

L.Icon.Default.mergeOptions({
  iconRetinaUrl: icon2x,
  iconUrl: icon,
  shadowUrl: shadow,
});

export const OSM_TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
export const OSM_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
export const DEFAULT_CENTER = [-6.9175, 107.6191]; // Bandung

export default L;