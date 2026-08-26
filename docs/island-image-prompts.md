# 首页群岛 · 四套方案 · AI 图片生成 Prompt 包

> 给 Midjourney / DALL·E 3 / Flux / Stable Diffusion / 即梦 / 通义万相 / 可灵 / 文心一格 等通用。
> 每套方案都给两种用法：① 一张全景图（直接当首页背景）② 五张单岛图（拼接进 HTML 更稳）。
>
> A · 现代等距 ｜ B · 水墨江南 ｜ C · 暖光油画 ｜ **D · 童趣绘本**（升级版"原来那种儿童风"）

---

## 0. 通用使用说明

### 出图分辨率与比例

| 用途 | 推荐比例 | 推荐分辨率 |
|---|---|---|
| 整张首页背景全景 | **16:9** 或 **21:9** | 2560×1440 / 3840×1620 |
| 单座岛单独出图（透明背景或纯色背景，方便抠图叠到 HTML） | **1:1** | 1024×1024 / 2048×2048 |
| 顶部 Banner | **3:1** | 1920×640 |

### 通用反向 prompt（所有方案都加）

```
text, letters, watermark, signature, logo, ui, interface, buttons,
childish cartoon, kawaii, chibi, anime face, baby style,
thick black outlines, oversaturated rainbow colors, neon,
photo-realistic, photograph, 3d render plastic look,
low quality, blurry, deformed, distorted perspective, mutated,
people faces, real human, crowd
```

### 各工具语法尾巴

- **Midjourney v6**：英文 prompt 末尾加 `--ar 16:9 --style raw --v 6.0 --s 250`，反向词放 `--no text,letters,childish cartoon,kawaii,thick outlines`
- **DALL·E 3 (ChatGPT)**：去掉所有 `--` 参数，把"wide cinematic 16:9 panoramic, no text or letters anywhere"写进描述里
- **Flux / SD**：可以照搬，反向 prompt 单独贴到 Negative Prompt 框
- **即梦 / 通义万相 / 可灵 / 文心一格**：用下面提供的**中文版**效果更好

### 一个小技巧

如果想保证"五座岛排成一行"的构图（AI 经常画不准），用**单岛分开生成 → 再合成**的方式更可靠：每岛 1:1 出图，PNG 透明背景，叠到一个手绘水面/天空 PNG 上。

---

## 方案 A · 现代等距 Modern Isometric

> 几何体块 + 莫兰迪色 + 发丝级描边，高端品牌插画质感。

### A-① 全景图 prompt（英文 · Midjourney/Flux 首选）

```
Wide panoramic isometric editorial illustration of five distinct
floating islands arranged in a row above calm sea at gentle dawn,
clean modern brand illustration style reminiscent of Stripe / Linear
/ Notion / dribbble-tier vector work, strict 30-degree isometric
projection, each island is an elliptical green platform with visible
brown soil cross-section below, each carrying ONE unique small
architectural cluster made of pure geometric blocks (cube with
slanted gable roof, cylinder tower, prism), three visible faces on
every block with subtle gradient lighting (top brightest, left
mid-tone, right shaded), no outlines or only 0.5px hairlines,
limited muted earth-tone palette: sage olive green grass, terracotta
clay roof, slate navy windows, cream walls, ochre accent, deep
brown soil, three layered distant mountains in cool blue-grey fading
into atmospheric haze, soft pale sun glow upper right, light sky
gradient from misty blue at top to warm cream at horizon, calm
seafoam-grey water with three or four gentle horizontal ripple
strokes, soft long shadow under each island floating on water,
balanced symmetric composition with breathing space, designer-grade,
museum quality, no text anywhere
```

### A-① 全景图 prompt（中文 · 即梦/通义/可灵首选）

```
横版超宽全景等距视角插画，五座漂浮岛屿一字排开在平静海面之上，
晨光氛围，高端品牌插画风格（参考 Stripe / Linear / dribbble 风格），
严格 30 度等距视角，每座岛是椭圆形绿色台面，下方可见棕色土层剖面，
每岛承载一组独特的几何体块小建筑（立方体+斜屋顶/圆柱小塔/三棱柱），
每个体块都有三个可见面，受光分明（顶部最亮、左侧中间调、右侧背光），
无描边或只有 0.5 像素发丝线，克制的莫兰迪色板：
鼠尾草绿草地、陶土色屋顶、板岩深蓝窗户、奶油色墙体、赭石色点缀、深棕土层；
背景三层远山在冷灰蓝中渐隐入大气雾霭，淡淡日晕在右上方，
天空从米雾蓝渐变到地平线暖奶油色，海面是海沫灰，
画三四笔横向涟漪点缀，每座岛下投长柔影漂浮在水面上，
对称均衡构图，留有呼吸空间，画面无任何文字
```

### A-② 单座岛 prompt（5 张，每张独立生成，1:1）

复用下面的**通用模板**，替换 `[ISLAND_X]` 里的描述即可。

```
Isometric editorial illustration of ONE small floating island on a
transparent or pure cream background, modern brand-illustration
style like Stripe / Linear, strict 30-degree isometric projection,
elliptical sage-olive green grass platform with visible deep-brown
soil cross-section below, [ISLAND_X], all buildings made of pure
geometric blocks with three visible faces and subtle gradient
lighting, no outlines or 0.5px hairlines only, muted earth-tone
palette (sage green, terracotta, slate navy, cream, ochre, deep
brown), soft long shadow below the island, single object centered,
no text, centered 1:1 square composition, designer-grade vector
```

| # | `[ISLAND_X]` 内容（替换进上面） |
|---|---|
| 档案岛 | `terracotta-roofed small classical library: a cream block with four thin white columns in front, a small triangular pediment in clay-red on top, a tiny golden owl-shaped sculpture on the ridge, a low brown bench, two cone-shaped sage trees beside it, a small black mailbox` |
| 健康岛 | `a cream canteen block with a tall slate-navy chef-hat-style chimney releasing a single round white steam puff, a small glass greenhouse beside it with tiny red tomatoes inside, a sage-green windmill with four ochre blades, one round apple tree, an orange running track loop around the perimeter` |
| 阅读岛 | `a tall cream cylindrical lighthouse with two terracotta horizontal bands, ochre glass lantern room on top, a small slate-navy peaked roof, a soft diffused beam of pale yellow light emerging horizontally, beside it a low open pavilion with two pillars holding up a sage-green flat roof, a stack of three small books in red/blue/yellow muted tones on a podium` |
| 活动岛 | `a striped circus-tent in muted terracotta and cream stripes with a small sage flag on top, beside it a tiny ferris-wheel silhouette in slate navy with six pastel-colored cabins, in front a small green soccer pitch with two goals` |
| 成就岛 | `a small Greek-style temple: five thin cream Doric columns supporting a clay-red triangular pediment, a slate-navy stepped base, in front a three-tier podium with a gold medal disc resting on the top tier, a small red carpet leading up to it` |

### A 反向 prompt（已包含通用，再补几个 A 专属）

```
brush strokes, painterly, photorealistic, plastic 3d, watercolor,
ink wash, traditional Chinese, anime, overly cute mascots
```

---

## 方案 B · 水墨江南 Ink Wash · Jiangnan

> 米纸底 + 墨色远山 + 粉墙黛瓦 + 一点朱砂，最有文化重量。

### B-① 全景图 prompt（英文 · MJ/Flux 首选）

```
Wide panoramic Chinese ink wash landscape painting of five small
Jiangnan-style island villages in a row on a calm misty lake at
gentle dawn, traditional Suzhou / Anhui (Huizhou) architecture with
whitewashed earthen walls, dark grey ceramic tile sloping roofs,
upturned eave corners, distinctive layered Ma Tau Wall (horse-head
stepped gable walls), each island has one to three small white
houses tucked among bamboo groves and a few pine trees, occasional
plum blossom branch silhouettes or willow strands, very sparse
vermillion-red accent only on tiny hanging lanterns and a single
seal stamp in the corner, three distant misty mountain ranges
fading into pale parchment sky, low contrast ink-grey on aged
ricepaper, soft round white moon or pale sun upper right with
faint halo, calm milky pale celadon water with very sparse ink
ripple strokes, atmospheric mist band between mid-ground and
background, classical sumi-e brush-ink texture with visible
ricepaper grain throughout, palette strictly: aged ricepaper cream
F4EAD6, ink black 2C2C2C, jade grey-green 6E8B82, taupe stone
7E7466, vermillion accent B85450 only, balanced empty space (留白)
composition, museum-quality cultural illustration, evoking Song
Dynasty landscape and Wu Guanzhong style, no bright colors, no text
```

### B-① 全景图 prompt（中文 · 即梦/通义/可灵首选）

```
横版超宽全景中国水墨长卷山水画，五座小江南岛屿村落一字排开
在雾气朦胧的平静湖面上，温柔的破晓氛围，
传统苏州 / 徽派建筑：白色夯土外墙、深灰陶瓦坡顶、翘角飞檐、层层叠叠的马头墙，
每座岛上有 1-3 间小白屋，掩映在竹林和几株松树之间，
偶尔点缀梅枝或柳条剪影，
朱砂红仅用作极少量点缀（小灯笼、角落一方印章），
背景三层墨色远山在大气雾霭中渐隐入米纸色天空，
低对比度的墨灰色，整体是泛黄米纸的底色，
柔和的圆形白月或淡淡日晕在右上方，
平静的乳白淡青色水面，几笔稀疏墨色涟漪，
中景和远景之间有一道横向雾带，
经典水墨写意笔触，整张画面看得见米纸纹理，
配色严格限制：陈旧米纸色 #F4EAD6、墨黑 #2C2C2C、青灰绿 #6E8B82、
土褐 #7E7466、朱砂仅作点缀 #B85450，
留白构图均衡，宋代山水 + 吴冠中风格，博物馆级文教插画，
无明亮饱和色彩，画面无任何文字
```

### B-② 单座岛 prompt 模板

```
Chinese ink wash painting of ONE small Jiangnan-style island village
on aged ricepaper background, traditional Suzhou architecture
(whitewashed walls, dark grey tile roof, upturned eaves, layered
horse-head gable wall), [ISLAND_X], muted ink palette only (cream
F4EAD6, ink 2C2C2C, jade grey 6E8B82, taupe 7E7466), single tiny
vermillion accent allowed, atmospheric soft fog around the base,
calm milky pale water at the foot, single object centered, sumi-e
brush texture, ricepaper grain visible, balanced empty space, 1:1
square composition, no text, classical Chinese landscape painting
quality
```

| # | `[ISLAND_X]` 内容 |
|---|---|
| 档案岛 | `a small scholar's study tower (书斋) with a two-tier curved tile roof, latticed wooden windows in dark grey, a single bamboo grove of seven slender stalks beside it, a small grey stone lantern in front, one tiny vermillion lantern hanging from the eave` |
| 健康岛 | `a long single-story Jiangnan canteen with a wide tile roof and three latticed windows showing soft warm interior glow, herb garden plots in front rendered as a few ink dots, two pine trees framing the building, a faint rising steam wisp from the chimney drawn as a single ink curl` |
| 阅读岛 | `an elegant 阁 pavilion of two stories with deeply curved upturned roof corners on both levels, surrounded by a low bamboo fence, a stone arch bridge curving toward it from the right, three lotus pads floating in the foreground water, one tiny vermillion ribbon tied to the upper roof corner` |
| 活动岛 | `a Jiangnan village square scene: three small white houses clustered around a stage with a tile roof, several tiny vermillion lanterns strung between the houses, a single tall plum tree in blossom in the corner using a few vermillion dots, no people visible just architecture and atmosphere` |
| 成就岛 | `a traditional Chinese 牌坊 stone memorial archway: three openings, dark grey stone, carved details, tile roof on top, two stone lion silhouettes flanking the base, vermillion accent only on a small horizontal plaque in the center` |

### B 反向 prompt（追加）

```
bright colors, neon, modern architecture, glass buildings, cars,
anime, kawaii, chibi, photo realistic, 3d render, plastic, oily
paint, oversaturated, western cartoon
```

---

## 方案 C · 暖光油画 Painted Dawn

> 晨光金天 + 雾蓝远山 + 现代校园建筑，温暖有电影感。

### C-① 全景图 prompt（英文 · MJ/Flux 首选）

```
Wide cinematic panoramic painted concept-art illustration of five
floating green islands in a row above calm reflective water at
golden-hour dawn, each island carrying ONE small modern school
campus building (sloped slate roof, large clean glass facade with
warm interior light glowing out, warm wood and cream wall accents,
small courtyard with a tree), painted in soft impressionist
concept-art style reminiscent of Studio Ghibli mid-shot backgrounds
and Makoto Shinkai morning landscapes and Joaquín Sorolla brushwork,
warm-to-cool palette: golden F2C078 sky top, peach E8A07A mid sky,
dusty blue 6E91B8 distant mountains, deep verdant 4F7858 island
grass, slate-navy 3A3F50 building structures, warm cream and wood
accents, three distinct layered distant mountain ranges fading into
soft morning mist, low soft sun in upper right with diffuse golden
ray bands through the haze, calm reflective water surface with
painted brushstroke ripples and faint island reflections, layered
painted vegetation (tall cone pines, rounded deciduous trees) with
soft gradient lighting, drift of warm fog band along the horizon,
low-contrast painterly aesthetic with soft brush-edge transitions
and no harsh outlines, picture-book-grade illustration, warm but
mature mood, atmospheric depth, balanced horizontal composition
with breathing space, no text anywhere
```

### C-① 全景图 prompt（中文 · 即梦/通义/可灵首选）

```
横版超宽电影感全景手绘概念插画，五座漂浮的绿色岛屿一字排开
在平静镜面水之上，黄金时刻破晓氛围，
每座岛上承载一组小型现代校园建筑（深灰板岩坡屋顶、大面积干净玻璃幕墙
透出温暖室内灯光、暖木色与奶油色饰面、小庭院里一棵树），
画风是柔和印象派概念插画，参考吉卜力中景背景、
新海诚晨光风景、Sorolla 油画笔触，
冷暖对比配色：天顶金黄 #F2C078、中段桃色 #E8A07A、
远山雾蓝 #6E91B8、岛屿深绿 #4F7858、建筑石板蓝 #3A3F50，
暖奶油色与木色点缀，
背景三层渐隐的远山没入晨雾，
低位柔和太阳在右上方透出几束金色光柱，
平静的镜面水面上有手绘笔触涟漪和淡淡的岛屿倒影，
分层手绘植被（高瘦松锥 + 圆形阔叶树），柔和受光，
地平线有一道温暖晨雾带，
低对比度油画质感，柔和笔触过渡，无硬描边，
高级绘本插画级别，温暖而成熟的氛围，
有大气深度，横向均衡构图留有呼吸空间，画面无任何文字
```

### C-② 单座岛 prompt 模板

```
Painted concept-art illustration of ONE small floating island with
a modern school campus building, transparent or warm cream
background, soft impressionist style like Studio Ghibli or Makoto
Shinkai morning backgrounds, deep verdant green grass on island top
with painterly tree shadows, warm-to-cool palette (golden, peach,
dusty blue, verdant green, slate navy, cream), [ISLAND_X],
soft brushstroke ripples and faint reflection in the water below
the island, atmospheric soft glow around, no harsh outlines,
single object centered, 1:1 square composition, picture-book
quality, no text
```

| # | `[ISLAND_X]` 内容 |
|---|---|
| 档案岛 | `a modern library: a low one-story building with a steep slate sloped roof, full-height glass facade across the front showing rows of warm-lit bookshelves inside, climbing ivy on one side, a single tall pine tree to the right, a small reading bench under the eaves` |
| 健康岛 | `a modern campus canteen/clinic: terracotta-warm facade with large floor-to-ceiling windows revealing a sun-lit kitchen with hanging copper pots, a herb garden of soft green dabs in front, a single fruit tree with painted golden orbs, a low fence` |
| 阅读岛 | `a 3-story tall central campus library with a tall sloped slate roof and a skylight cupola on top doubling as a small lighthouse, full glass facade glowing warm yellow from inside, a tall red flag on a slender pole beside it, two tall painted pine trees flanking the entrance, gentle stone steps leading up from the water` |
| 活动岛 | `a modern campus gymnasium with a low circular dome roof in dusty blue, large arched glass entrance glowing warm from within, a small outdoor amphitheater of stone steps in front, a single colorful banner` |
| 成就岛 | `a modern interpretation of a classical assembly hall: five slender cream columns supporting a deep slate-grey triangular pediment, a clay-red banner draped above the entrance, warm golden light spilling out of the doorway onto the steps, two cone-shaped pines flanking the entrance` |

### C 反向 prompt（追加）

```
flat vector, isometric, ink wash, traditional Chinese, anime girl
faces, chibi, photo-real people, neon colors, harsh outlines,
oversaturated, cell shading, kawaii, low quality, blurry, ugly
```

---

## 方案 D · 童趣绘本 Storybook Whimsy

> 在原来那套手绘 SVG 的基础上"升级"：保留可爱、温暖、繁茂细节，但用 AI 出图后远比手绘更精致 — 像 Pixar / 动森 / Mary Blair 的童书地图，**不再卡通到幼稚**。最适合面向小学生 / 家长。

### D-① 全景图 prompt（英文 · MJ / Flux 首选）

```
Wide panoramic charming storybook illustration of FIVE clearly
separate small floating ISLANDS arranged in a row over open
turquoise sea on a bright sunny morning. CRITICAL: each island is
an obvious discrete island, not a mountain or hill — every island
has a flat-ish green grass top, a clear pale-yellow sandy beach
rim around the edge, and a visible brown soil and rock cross-section
cliff underneath, ALL fully surrounded by water on every side, with
visible open turquoise sea separating each island from the next
(generous water gaps between islands). The islands sit on water,
not connected by any land bridge or continuous shoreline.

Style: premium children's picture-book art quality reminiscent of
Mary Blair concept art, Disney Animal Kingdom park map, Animal
Crossing New Horizons aesthetic, Richard Scarry detailed busy-page
style. Soft hand-drawn watercolor + gouache, warm cream-brown
outlines (NOT harsh black).

Each island PACKED with delightful small details on top: cozy
storybook buildings, winding stone paths, benches, fruit trees,
flowers, paper lanterns, butterflies, signposts, mushrooms.

Palette: cream walls #FFF6DD, brick-red roofs #E8584A, sunny yellow
#FFE672, fresh grass green #7DD16B, sky blue #A8DDF0, warm sand
beach #FFE0B2, soft pink #FFB8C9, brown outline & soil cliff #5A3712,
exposed earth tones #A06B3C.

Background: big happy round sun upper right with soft yellow rays
(NO face), fluffy cumulus clouds, three layers of soft distant
mountains in dusty blue-purple ON THE FAR HORIZON (clearly behind
the islands, not connected). Calm turquoise water with sparkly
highlights and gentle ripples filling the foreground and between
the islands, two or three little sailboats / hot-air balloons
drifting. Soft drop shadow under each island sitting on the water.
Dense joyful composition but visually balanced, family-friendly,
warm welcoming mood. NO text, NO faces on inanimate objects, NO
kindergarten scribbles.
```

### D-① 全景图 prompt（中文 · 即梦 / 通义 / 可灵 / 文心一格首选）

```
横版超宽全景治愈系童书风插画，
画面是五座【明确独立、互相分开】的【海中小岛】一字排开，
晴朗清晨，背景是开阔的青绿色海面。

【关键 · 一定要按这条画】：
每一座都必须是【独立的小岛】，不是山，不是丘陵，
每座岛是一块绿色草地顶台，岛边一圈淡黄色沙滩，
草地下面有一段棕色泥土+岩石的剖面悬崖，
【四面环水】，可以清楚看到岛之间有开阔的青绿色海水相隔，
五座岛之间有【宽阔的水面间隙】，绝对不能用陆地连起来，
也不要画成一片连续的山岭或者陆地凸起。

风格：高级儿童绘本水准，参考 Mary Blair 概念图、迪士尼动物王国
乐园地图、动森新地平线美术、Richard Scarry 繁茂童书插画风格，
柔和的手绘水彩+水粉笔触，暖奶油棕色描边（不是刺眼黑边）。

岛上装满讨人喜爱的小细节（温馨小房子、蜿蜒石板小径、长椅、
果树、鲜花、纸灯笼、蝴蝶、指示牌、小蘑菇）。

配色：奶油墙 #FFF6DD、砖红屋顶 #E8584A、暖黄 #FFE672、
嫩绿草地 #7DD16B、天空蓝 #A8DDF0、暖沙滩 #FFE0B2、
柔粉 #FFB8C9、棕色描边 & 土壤剖面 #5A3712、裸土 #A06B3C。

背景：右上方一个温柔的圆太阳，柔和黄色光线（太阳不要画脸！），
天空有蓬松积云，远方地平线上有三层柔和的蓝紫色远山
（远山只能在地平线后方远远的地方，不能跟岛连在一起）。
中景和前景全部是平静的青绿色海面，
岛与岛之间能清楚看见水面，水面有粼粼波光和柔和涟漪，
两三只小帆船或热气球漂浮其中，
每座岛下方有柔和投影坐在水面上。

画面繁茂热闹但整体均衡，家庭友好，温暖欢迎的氛围。
画面禁止：任何文字字母、太阳/云朵上画脸、幼儿园涂鸦感、
把五座岛画成连绵的山、画成一块完整大陆。
```

### D-② 单座岛 prompt 模板（5 张，每张独立生成，1:1）

每张图都是【一座漂浮在水里的独立小岛】（不是山、不是山头、不是丘）。
模板英文版（推荐 Midjourney / Flux）：

```
Charming storybook illustration of ONE small standalone floating
ISLAND, completely surrounded by bright turquoise water on every
side, with soft pastel sky background.

ISLAND SHAPE: a clearly defined oval green grass top platform, with
a pale-yellow sandy beach rim around the entire edge, and a visible
brown soil + rock cliff cross-section dropping into the water below
(showing exposed earth tones #5A3712 and #A06B3C). The island sits
on/floats above the water surface with a soft drop shadow and gentle
ripples lapping against the beach. It must look UNAMBIGUOUSLY like
a tiny island, not a mountain, not a hilltop, not a piece of land.

Style: premium children's picture-book art like Mary Blair / Disney
Animal Kingdom park map / Animal Crossing / Richard Scarry, soft
watercolor + gouache with warm cream-brown outlines (NOT harsh
black).

ON TOP OF THE ISLAND: [ISLAND_X], packed with delightful supporting
details (little stone paths, signposts, flowers, butterflies,
mushrooms, lanterns, benches).

Palette: cream FFF6DD, brick-red E8584A, sunny yellow FFE672, grass
green 7DD16B, sky blue A8DDF0, sandy beach FFE0B2, soft pink FFB8C9,
brown outline & soil 5A3712, earth A06B3C.

Composition: single island centered, 1:1 square, soft fluffy clouds
above, sparkly water ripples around the base, warm welcoming
family-friendly mood, high detail. NO text, NO faces on inanimate
objects, NOT a mountain, NOT a hill.
```

模板中文版（推荐即梦 / 通义 / 可灵 / 文心一格）：

```
童书风格插画，画一座【单独的小岛】，
四面环绕着青绿色的海水，背景是柔和的淡色天空。

【岛屿形状】（必须严格按这条）：
一块椭圆形绿色草地顶台，岛边一圈淡黄色沙滩，
草地下方有一截棕色泥土加岩石的剖面悬崖落入海中，
能看见岛的边缘和水线、岛下方有柔和投影漂浮在水面上，
水面有轻柔涟漪拍打沙滩。
必须明确地像一座【海中小岛】，
不是山，不是山头，不是丘陵，不是大陆的一角。

【画风】：高级儿童绘本水准，
参考 Mary Blair 概念图、迪士尼动物王国乐园地图、动森、
Richard Scarry 童书风格，
柔和水彩+水粉笔触，暖奶油棕色描边（不是黑色硬边）。

【岛上画什么】：[ISLAND_X]，
配以丰富的小细节（蜿蜒石板小径、指示牌、鲜花、蝴蝶、
小蘑菇、纸灯笼、长椅）。

【配色】：奶油 #FFF6DD、砖红 #E8584A、暖黄 #FFE672、
嫩绿 #7DD16B、天空蓝 #A8DDF0、沙滩 #FFE0B2、
柔粉 #FFB8C9、棕色描边 & 土壤 #5A3712、裸土 #A06B3C。

【构图】：单座岛居中，1:1 方形，上方有蓬松小云朵，
岛周围水面有粼粼波光，温暖治愈，细节丰富。
禁止：文字字母、给死物画脸、画成山或山头、画成连续陆地。
```

| # | `[ISLAND_X]` 内容（替换进上面） |
|---|---|
| 档案岛 | `on top of the island grass platform there is a cozy small classical library / hall of records with cream stone walls, four small white columns in front, a clay-red triangular pediment with a tiny golden owl statue on top, two arched stained-glass windows; beside it a small clock tower with a navy roof; in front a tiny book-stall kiosk with yellow awning, a wooden reading bench with a small lamp, an open book sculpture on a stone pedestal; two cone-shaped trees framing it, a friendly mailbox, a string of paper lanterns strung between poles, a butterfly fluttering nearby. All buildings and props sit safely inside the green grass platform, never hanging off the beach edge.` |
| 健康岛 | `on top of the island grass platform there is a friendly small canteen with a giant white chef's-hat-shaped roof on cream walls, a red brick chimney puffing a single tiny cloud, a yellow signboard; beside it a small glass greenhouse showing red tomatoes and yellow lemons inside; a cheerful pinwheel windmill with yellow blades; an apple tree heavy with red apples; a juice stall with striped orange-and-yellow awning and three glass bottles; a small circular running track with painted lane lines hugging the perimeter just inside the grass; a tiny fountain; vegetable patches with carrots and tomatoes. All structures sit safely inside the green grass platform.` |
| 阅读岛 | `on top of the island grass platform there is a tall slender lighthouse with cream and red horizontal stripes, a golden glass lantern room on top emitting soft yellow beams left and right, a small red flag on the spire; beside it an open-air reading pavilion with four white columns supporting a sky-blue roof, a stack of three colorful books (red, yellow, blue) on a pedestal; three tiny mushrooms, a wooden bench with a small lantern, an open book floating with magical sparkles, a friendly trail of paw prints leading to it, a butterfly. All sit safely on the green grass platform, sandy beach visible all around the edge.` |
| 活动岛 | `on top of the island grass platform there is a cheerful red-and-white striped circus tent with a small yellow flag on top; beside it a tiny ferris wheel with six pastel-colored cabins (pink, yellow, mint, blue, peach, lavender); a small art easel with a colorful painting; a soccer pitch with two tiny goals; two festival flags strung between poles; a hot-air balloon hovering above; a small drum; a stage with red curtains; a friendly signpost. All structures sit safely on the green grass platform, sandy beach visible all around the edge.` |
| 成就岛 | `on top of the island grass platform there is a charming small Greek-style temple with five cream Doric columns supporting a clay-red triangular pediment; on top sits a giant golden trophy cup; a red carpet leads up three white marble steps; on the carpet three podium tiers with gold/silver/bronze medal discs; golden stars float in the air with sparkle trails; two cone-shaped trees flanking; a friendly little laurel wreath, festive bunting flags, a tiny rosette ribbon. All sit safely on the green grass platform, sandy beach visible all around the edge.` |

### D 反向 prompt（追加在通用反向后）

```
mountain, mountains, hill, hillside, hilltop, mountain peak,
mountain range, cliff face on land, continuous landmass,
peninsula, plateau, attached land, land bridge connecting islands,
islands merging into each other, valley between hills,
buildings on a mountain, no water around the building,
faces on the sun, faces on clouds, googly eyes on objects,
kindergarten scribble, ugly proportions, deformed buildings,
oversaturated rainbow vomit, harsh pure black outlines,
photorealistic, 3d plastic render, anime girl, chibi, scary,
creepy, dark mood, gothic, low quality, blurry, jpeg artifacts,
distorted perspective, MS Paint, clipart
```

### D 关键词增强：要"岛感"必加这几个英文短语

- `tiny floating island with sandy beach rim`
- `surrounded by water on all sides`
- `visible brown soil cliff cross-section under the grass`
- `water gap between each island`
- `archipelago of five distinct islands`
- `island sits ON the water, not on land`

### D 风格关键词补充（如果工具支持"风格"下拉）

- Midjourney 适配："children's storybook, Mary Blair, Animal Crossing aesthetic, Pixar concept art, picture book illustration"
- DALL·E 3：直接在 prompt 里说 "in the style of a high-end children's picture book illustrator, like Mary Blair or Richard Scarry"
- 即梦/通义：风格选「儿童插画」「治愈系」「绘本」；如有"细节程度"调到最高
- 可灵：风格选「童趣」「迪士尼风」

---

## 1. 不同工具的微调建议

### Midjourney v6 / v6.1
- 把"英文全景 prompt"复制 → 末尾追加 `--ar 16:9 --style raw --v 6.1 --s 250 --no text,letters,kawaii,thick outlines`
- 想让风格更稳定：每张图都用相同的 `--sref [图片URL]` 锁风格
- 出完一张满意的全景后，把它当 `--cref` 去生成 5 张单岛，能保证风格一致

### DALL·E 3 (ChatGPT / Bing)
- 不支持 `--` 参数 → 删掉
- 在 prompt 开头加一句："Please generate exactly as described, do NOT add any text, letters, words, or labels in the image."
- DALL·E 3 比较容易加文字，反向词必须强调

### Stable Diffusion / Flux
- Flux 1.1 [pro] 对长 prompt 理解最好，直接贴
- SDXL 类的把 prompt 拆短，每个 island 单独生成
- Negative Prompt 框：贴通用反向 + 方案专属反向

### 即梦 / 通义万相 / 可灵 / 文心一格
- 用**中文版本** prompt 效果最好
- 比例选择"宽幅 16:9"或"横版 3:2"
- 风格选择：方案 A 选"扁平插画/2.5D" · 方案 B 选"水墨/国风" · 方案 C 选"概念插画/油画"
- 如果支持负面词，把通用反向贴进去

### Adobe Firefly
- 风格预设建议：方案 A → "矢量插图 / 等距图" · 方案 B → "水墨 / 浓墨" · 方案 C → "数字绘画 / 印象派"
- 在"参考图"里塞一张参考能极大提升一致性

---

## 2. 拿到图之后怎么用

### 用法 ① 直接当全景背景
1. 出一张 2560×1440 的横向全景
2. 把它存到 `assets/bg-scheme-X.png`
3. 我帮你改 `island-homepage.html`，把背景换成这张图，热点位置按图重新定位

### 用法 ② 五张单岛 + 我手绘水面/天空（推荐，最可控）
1. 出 5 张 1024×1024 的单岛 PNG（带透明背景或纯色背景）
2. 出一张 2560×800 的纯天空 + 水面背景图
3. 我用 CSS 绝对定位把 5 张岛叠到背景上，热点可点
4. 优点：每座岛清晰、可单独替换、文件小、性能好

如果选用法 ②，记得让 AI 工具**导出 PNG 带 alpha 通道**（即梦/Midjourney 默认 JPG，需要导出后用 remove.bg 抠图，或者直接生成时背景指定"纯色 + 我会抠掉"）。

---

## 3. 我的推荐

如果你只想试一次：
- **教育博览会要镇得住** → **方案 B 水墨江南**（独一无二、有文化高度、不撞设计稿）
- **拍 50 分稳照** → 用**方案 C 暖光油画**（最容易出彩、最温暖、家长老师都接受）
- **要做品牌系统/能扩展到名片/PPT** → **方案 A 现代等距**（最容易二次复用）
- **小朋友是主用户、要好玩可爱** → **方案 D 童趣绘本**（升级版"原来那种"，但精度远比手绘 SVG 高）

如果时间允许，建议先各出一张全景图对比，然后选一套出 5 张单岛 1:1。

挑好以后把图发我，我把 HTML 改了就能上线。

---

## 4. 一次性把四套都跑一遍的 batch 写法

如果你用 Midjourney 或类似工具想"一次跑四套全景对比"，可以这样：

```
/imagine prompt: [A 全景 prompt 英文版] --ar 16:9 --style raw --v 6.1
/imagine prompt: [B 全景 prompt 英文版] --ar 16:9 --style raw --v 6.1
/imagine prompt: [C 全景 prompt 英文版] --ar 16:9 --style raw --v 6.1
/imagine prompt: [D 全景 prompt 英文版] --ar 16:9 --style raw --v 6.1
```

四张并列对比之后，挑一套，再跑这套的 5 张单岛即可（每套总共 6 次出图）。
