// Access tokens intentionally live only in this module's memory. Refresh
// tokens are never exposed to JavaScript; the backend rotates them in an
// HttpOnly cookie.
let accessToken: string | null = null;

export const tokenStorage = {
  getAccessToken: (): string | null => accessToken,
  setAccessToken: (value: string): void => {
    accessToken = value;
  },
  clear: (): void => {
    accessToken = null;
  },
};
