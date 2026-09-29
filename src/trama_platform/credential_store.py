"""Secrets live only in Windows Credential Manager."""

import os

SECRET_NAMES = frozenset(
    {"api_token", "gateway_token", "utopia_token", "cccc_bridge_token"}
)


class CredentialStore:
    service = "TRAMA"

    def validate(self, name: str, value: str) -> None:
        self._check(name)
        if not value or len(value) > 2000:
            raise ValueError("La credencial debe tener entre 1 y 2000 caracteres")
        try:
            value.encode("ascii")
        except UnicodeEncodeError:
            raise ValueError(
                "El token debe usar caracteres ASCII válidos para Authorization Bearer"
            ) from None
        allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~+/="
        if any(char not in allowed for char in value) or "=" in value.rstrip("="):
            raise ValueError(
                "El token tiene caracteres o relleno no válidos para Authorization Bearer"
            )

    def _backend(self):
        if os.name != "nt":
            raise RuntimeError("El almacén de credenciales requiere Windows")
        try:
            from keyring.backends.Windows import WinVaultKeyring

            return WinVaultKeyring()
        except Exception:
            raise RuntimeError("Credenciales de Windows no está disponible") from None

    def _check(self, name: str) -> None:
        if name not in SECRET_NAMES:
            raise ValueError("Nombre de credencial no permitido")

    def get(self, name: str) -> str | None:
        self._check(name)
        if os.name != "nt":
            return None
        try:
            return self._backend().get_password(self.service, name)
        except Exception:
            raise RuntimeError("No se pudo consultar Credenciales de Windows") from None

    def has(self, name: str) -> bool:
        return bool(self.get(name))

    def set(self, name: str, value: str) -> None:
        self.validate(name, value)
        try:
            self._backend().set_password(self.service, name, value)
        except Exception:
            raise RuntimeError("No se pudo guardar la credencial en Windows") from None

    def delete(self, name: str) -> None:
        self._check(name)
        try:
            backend = self._backend()
            if backend.get_password(self.service, name) is not None:
                backend.delete_password(self.service, name)
        except Exception:
            raise RuntimeError("No se pudo borrar la credencial de Windows") from None
