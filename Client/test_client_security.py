"""Pruebas de credenciales de usuario en la CLI."""

import unittest
from unittest.mock import patch

from Client.client import token_para_usuario


class TestCredencialCliente(unittest.TestCase):
    def test_cli_usa_solo_el_token_individual_configurado(self):
        with patch.dict("os.environ", {
            "DFS_DEFAULT_USER": "ana",
            "DFS_USER_TOKEN": "secreto-de-ana",
            "DFS_USERS": '{"ana":"secreto-de-ana","luis":"secreto-de-luis"}',
        }):
            self.assertEqual(token_para_usuario(), "secreto-de-ana")

    def test_cli_no_puede_cambiar_a_otro_usuario(self):
        with patch.dict("os.environ", {
            "DFS_DEFAULT_USER": "ana",
            "DFS_USER_TOKEN": "secreto-de-ana",
        }, clear=True):
            with self.assertRaisesRegex(ValueError, "no puede cambiar"):
                token_para_usuario("luis")

    def test_cli_rechaza_ausencia_de_token(self):
        with patch.dict("os.environ", {"DFS_DEFAULT_USER": "ana"}, clear=True):
            with self.assertRaisesRegex(ValueError, "DFS_USER_TOKEN"):
                token_para_usuario()


if __name__ == "__main__":
    unittest.main()
