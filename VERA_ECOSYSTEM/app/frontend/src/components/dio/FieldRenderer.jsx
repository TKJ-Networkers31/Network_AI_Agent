import TextField from "./Field/TextField.jsx";
import NumberField from "./Field/NumberField.jsx";
import PasswordField from "./Field/PasswordField.jsx";
import SelectField from "./Field/SelectField.jsx";
import RadioField from "./Field/RadioField.jsx";
import CheckboxField from "./Field/CheckBoxField.jsx";
import SwitchField from "./Field/SwitchField.jsx";
import SliderField from "./Field/SliderField.jsx";
import DateField from "./Field/DateField.jsx";
import TimeField from "./Field/TimeField.jsx";
import FileField from "./Field/FileField.jsx";
import TableField from "./Field/TableField.jsx";
import InfoField from "./Field/InfoField.jsx";
import DividerField from "./Field/DividerField.jsx";
import ButtonField from "./Field/ButtonField.jsx";
import LocationPermissionField from "./Field/LocationPermissionField.jsx";
import ImageField from "./Field/ImageField.jsx";
import GalleryField from "./Field/GalleryField.jsx";
import ProgressField from "./Field/ProgressField.jsx";
import SvgField from "./Field/SvgField.jsx";

// Mapping tunggal field.type -> komponen.
const FIELD_COMPONENTS = {
  text: TextField,
  textarea: TextField,
  number: NumberField,
  password: PasswordField,
  select: SelectField,
  multiselect: CheckboxField,
  radio: RadioField,
  checkbox: CheckboxField,
  switch: SwitchField,
  slider: SliderField,
  date: DateField,
  time: TimeField,
  file: FileField,
  table: TableField,
  info: InfoField,
  divider: DividerField,
  button: ButtonField,
  image: ImageField,
  gallery: GalleryField,
  progress: ProgressField,
  svg: SvgField,
  location_permission: LocationPermissionField,
};

export default function FieldRenderer({ field, value, error, onChange, onAction }) {
  const Component = FIELD_COMPONENTS[field.type];

  if (!Component) {
    return (
      <div className="text-xs text-[#F59E0B] bg-[#F59E0B]/10 border border-[#F59E0B]/30 rounded-2xl px-3 py-2">
        Tipe field tidak dikenal: <code>{field.type}</code>
      </div>
    );
  }

  // Field bertipe "button" atau "location_permission" tidak punya
  // value/onChange biasa - keduanya trigger onAction sendiri (yang
  // terakhir sambil menyisipkan koordinat lewat extraValues).
  const ACTION_ONLY_TYPES = new Set(["button", "location_permission"]);
  const DISPLAY_ONLY_TYPES = new Set(["image", "gallery", "progress", "svg"]);

  if (ACTION_ONLY_TYPES.has(field.type)) {
    return <Component field={field} onAction={onAction} />;
  }
  if (DISPLAY_ONLY_TYPES.has(field.type)) {
    return <Component field={field} />;
  }

  return <Component field={field} value={value} onChange={(v) => onChange(field.id, v)} error={error} />;
 
}