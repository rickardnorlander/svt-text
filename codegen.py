import os
from PIL import Image
import base64

code = ['# generated code', 'files = {']
for fn in os.listdir('svt_text/tiles'):
    with open('svt_text/tiles/' + fn, 'rb') as f:
        content = base64.b64encode(f.read()).decode('ascii')
        fnsafe = fn.replace('\'', '\\\'')
        code.append('  \'%s\': b\'%s\',' % (fnsafe, content))
code.append('}')
with open('svt_text/generated.py', 'w') as f:
    f.write('\n'.join(code))
