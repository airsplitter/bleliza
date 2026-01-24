import shutil
import os

zip_name = 'bleliza_utilities'
dir_name = 'bleliza_utilities'

# Remove old zip if it exists
if os.path.exists('bleliza_texturetools.zip'):
    os.remove('bleliza_texturetools.zip')
    print("Old zip removed.")

if os.path.exists(f'{zip_name}.zip'):
    os.remove(f'{zip_name}.zip')

shutil.make_archive(zip_name, 'zip', '.', dir_name)
print(f"{zip_name}.zip created successfully.")
