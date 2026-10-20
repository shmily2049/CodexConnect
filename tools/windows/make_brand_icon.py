from pathlib import Path
import base64
from io import BytesIO
from PIL import Image,ImageDraw

work = Path(__file__).resolve().parent
source = work.parents[1] / 'src'
im = Image.new('RGBA',(1024,1024))
d = ImageDraw.Draw(im)
d.rounded_rectangle((32,32,992,992),radius=220,fill='#6C59D9')
d.arc((210,345,590,680),90,270,fill='white',width=50)
d.arc((434,345,814,680),270,450,fill='white',width=50)
d.rounded_rectangle((380,487,644,537),radius=25,fill='white')
im.save(work/'brand.icns',format='ICNS')
im.save(work/'brand.ico',format='ICO',sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
small=im.resize((64,64),Image.Resampling.LANCZOS)
blob=BytesIO();small.save(blob,format='PNG')
(source/'app_icon.py').write_text('"""Application icon, shared by desktop builds."""\nPNG = '+repr(base64.b64encode(blob.getvalue()).decode())+'\n',encoding='utf-8')
