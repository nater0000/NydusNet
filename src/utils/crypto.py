import os
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
from cryptography.fernet import Fernet, InvalidToken
import base64
import secrets
import logging

class CryptoManager:
    """
    Handles client-side encryption and decryption of configuration data
    using a master password and a recovery key system.
    """
    def __init__(self):
        # Path for the encrypted recovery key file
        self.recovery_key_file = os.path.join(os.getenv('APPDATA'), 'NydusNet', 'SyncData', 'recovery.dat')
        
    def _derive_key(self, password: str, salt: bytes) -> bytes:
        """Derives a cryptographic key from a password/key and a salt."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000, # High number of iterations for security
            backend=default_backend()
        )
        return base64.urlsafe_b64encode(kdf.derive(password.encode()))

    def encrypt_data(self, data: bytes, password: str) -> bytes:
        """Encrypts data using the provided password."""
        salt = os.urandom(16)
        key = self._derive_key(password, salt)
        f = Fernet(key)
        encrypted_data = f.encrypt(data)
        return salt + encrypted_data

    def decrypt_data(self, encrypted_data_with_salt: bytes, password: str) -> bytes | None:
        """
        Decrypts data using the provided password. Returns None on failure.
        """
        try:
            salt = encrypted_data_with_salt[:16]
            encrypted_data = encrypted_data_with_salt[16:]
            
            key = self._derive_key(password, salt)
            f = Fernet(key)
            
            return f.decrypt(encrypted_data)
        except InvalidToken:
            logging.warning("Decryption failed: Invalid master password or recovery key.")
            return None
        except Exception as e:
            logging.error(f"An unexpected decryption error occurred: {e}")
            return None

    def generate_recovery_key(self) -> str:
        """
        Generates a new, secure recovery key.
        This should be displayed to the user once and they should be told to save it.
        """
        return secrets.token_urlsafe(24)
        
    def save_recovery_key(self, recovery_key: str, master_password: str):
        """Encrypts and saves the recovery key to a file using the master password."""
        try:
            encrypted_key = self.encrypt_data(recovery_key.encode('utf-8'), master_password)
            with open(self.recovery_key_file, 'wb') as f:
                f.write(encrypted_key)
            logging.info("Recovery key saved successfully.")
        except Exception as e:
            logging.error(f"Failed to save recovery key: {e}", exc_info=True)

    def get_recovery_key(self, master_password: str) -> str | None:
        """Decrypts and returns the recovery key from the file."""
        if not os.path.exists(self.recovery_key_file):
            logging.warning("Recovery key file not found.")
            return None

        try:
            with open(self.recovery_key_file, 'rb') as f:
                encrypted_key = f.read()
            
            decrypted_key = self.decrypt_data(encrypted_key, master_password)
            if decrypted_key:
                return decrypted_key.decode('utf-8')
            else:
                logging.warning("Failed to decrypt recovery key.")
                return None
        except Exception as e:
            logging.error(f"Failed to retrieve recovery key: {e}", exc_info=True)
            return None

    def re_encrypt_with_new_password(self, encrypted_data_with_salt: bytes, old_key: str, new_password: str) -> bytes | None:
        """
        Decrypts data with an old key (password or recovery key) and re-encrypts
        it with a new password. Returns the new encrypted data.
        """
        decrypted_data = self.decrypt_data(encrypted_data_with_salt, old_key)
        if decrypted_data:
            return self.encrypt_data(decrypted_data, new_password)
        return None
