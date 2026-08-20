export function formatEIN(value = '') {
  const digits = String(value).replace(/\D/g, '').slice(0, 9);
  if (digits.length <= 2) return digits;
  return `${digits.slice(0, 2)}-${digits.slice(2)}`;
}

export function rawEIN(value = '') {
  return String(value).replace(/\D/g, '').slice(0, 9);
}