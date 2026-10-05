// src/utils/leaflet.js
// Satu pintu import Leaflet: memperbaiki ikon marker default yang rusak di bundler Vite.
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import icon2x from "leaflet/dist/images/marker-icon-2x.png";
import icon from "leaflet/dist/images/marker-icon.png";
import shadow from "leaflet/dist/images/marker-shadow.png";

// Leaflet mencoba menebak path ikon lewat CSS, yang gagal setelah di-bundle.
delete L.Icon.Default.prototype._getIconUrl;

L.Icon.Default.mergeOptions({
  iconRetinaUrl: icon2x,
  iconUrl: icon,
  shadowUrl: shadow,
});

export default L;