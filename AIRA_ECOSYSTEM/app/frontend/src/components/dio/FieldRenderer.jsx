import TextField from "./Field/TextField.jsx";
import NumberField from "./Field/NumberField.jsx";
import PasswordField from "./Field/PasswordField.jsx";
import SelectField from "./Field/SelectField.jsx";
import RadioField from "./Field/RadioField.jsx";
import CheckboxField from "./Field/CheckboxField.jsx";
import SwitchField from "./Field/SwitchField.jsx";
import SliderField from "./Field/SliderField.jsx";
import DateField from "./Field/DateField.jsx";
import TimeField from "./Field/TimeField.jsx";
import FileField from "./Field/FileField.jsx";
import TableField from "./Field/TableField.jsx";
import InfoField from "./Field/InfoField.jsx";
import DividerField from "./Field/DividerField.jsx";
import ButtonField from "./Field/ButtonField.jsx";

// Mapping tunggal field.type -> komponen. Ini SATU-SATUNYA tempat
// yang tahu nama tipe field - tidak ada switch/if berdasarkan nama
// fitur/domain di mana pun di renderer ini.
const FIELD_COMPONENTS = {
  text: TextField,
  textarea: TextField,
  number: NumberField,
  password: PasswordField,
  select: SelectField,
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

  // Field bertipe "button" tidak punya value/onChange - dia trigger
  // onAction seperti ActionBar, cuma posisinya inline dalam section.
  if (field.type === "button") {
    return <Component field={field} onAction={onAction} />;
  }

  return (
    <Component field={field} value={value} onChange={(v) => onChange(field.id, v)} error={error} />
  );
}