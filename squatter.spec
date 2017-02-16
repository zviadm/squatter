# -*- mode: python -*-

from kivy.tools.packaging.pyinstaller_hooks import get_deps_all, hookspath, runtime_hooks
block_cipher = None


a = Analysis(['squatter.py'],
             pathex=['/Users/zviad/Dropbox (Personal)/Documents/Projects/squatter'],
             binaries=[],
             datas=[('squatter.kv', '.')],
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=['_tkinter', 'Tkinter', 'enchant', 'twisted'],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          exclude_binaries=True,
          name='squatter',
          debug=False,
          strip=False,
          upx=True,
          console=False )
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               name='squatter')
app = BUNDLE(coll,
             name='squatter.app',
             icon=None,
             bundle_identifier=None)
