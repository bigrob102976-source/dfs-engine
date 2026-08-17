const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function isValidEmail(value: string): boolean {
  return typeof value === "string" && value.length <= 254 && EMAIL_PATTERN.test(value);
}

export const MIN_PASSWORD_LENGTH = 8;

export function isValidPassword(value: string): boolean {
  return typeof value === "string" && value.length >= MIN_PASSWORD_LENGTH && value.length <= 512;
}

export function normalizeEmail(value: string): string {
  return value.trim().toLowerCase();
}
