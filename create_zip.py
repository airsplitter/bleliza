import shutil
import os

if os.path.exists('bleliza_texturetools.zip'):
    os.remove('bleliza_texturetools.zip')

shutil.make_archive('bleliza_texturetools', 'zip', '.', 'bleliza_texturetools')
print("Zip file created successfully.")
