"""互換レイヤー（段階移行用）

既存コードが `runtime_settings` を import しているため、このファイルは
`settings.runtime` の値を再エクスポートするだけにします。
"""

from settings.runtime import *  # noqa: F401,F403
