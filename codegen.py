import base64
import io
import os

import numpy as np
from PIL import Image

TWOP = np.array([1,2,4,8,16,32,64,128], dtype=np.uint8)

code = ['# generated code\nnames = [']
image_bytes = []
for fn in os.listdir('svt_text/tiles'):
    with open('svt_text/tiles/' + fn, 'rb') as f:
        fn = fn.replace('\'', '\\\'')
        code.append('  \'%s\',' % fn)

        content = f.read()
        f = io.BytesIO(content)
        im = Image.open(f)
        data = np.asarray(im.getdata())
        color_index_0 = data[0]
        for x in data:
            if x != color_index_0:
                color_index_1 = x
                break

        onebit = data == color_index_0
        key = tuple(np.dot(onebit.reshape(-1, 8), TWOP))
        image_bytes.append(bytes(key))

code.append(']')
code.append('files = %s\n' % base64.b64encode(b''.join(image_bytes)))
with open('svt_text/generated.py', 'w') as f:
    f.write('\n'.join(code))
