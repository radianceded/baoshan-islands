/* =============================================================================
 *  教育专家数据展示面板 —— 数据接口层 / DATA INTERFACE
 * -----------------------------------------------------------------------------
 *  把你们网站的真实数据接到这里即可，无需改动可视化代码。
 *
 *  两种接法（任选其一）：
 *
 *  ① 直接对接后端 API（推荐）
 *     - 把 USE_MOCK 改为 false
 *     - 填写 API_URL 为你们的接口地址（返回 JSON，字段结构见下方 SHAPE）
 *     - 如接口字段名和本文件不一致，在 mapApiResponse() 里做一次字段映射
 *     面板每 REFRESH_MS 毫秒自动拉取一次，实现“实时”刷新。
 *
 *  ② 先用静态数据 / 手动更新
 *     - 保持 USE_MOCK = true
 *     - 直接修改下方 MOCK_DATA 里的数字即可
 * ========================================================================== */

const USE_MOCK   = false;                                   // ← 接真实接口时改为 false
const API_URL    = '/api/dashboard'; // ← 换成你们的接口地址
const REFRESH_MS = 30000;                                   // 自动刷新间隔（毫秒）

/* -----------------------------------------------------------------------------
 *  数据结构 SHAPE —— 你们接口需要返回（或被 mapApiResponse 映射成）这个结构：
 *
 *  {
 *    kpi: {
 *      works, likes, comments, views, schools,      // 总量
 *      likesToday, commentsToday, viewsToday        // 今日新增
 *    },
 *    awards:  [ { label, value, color } ],          // 奖项等级分布（环形图）
 *    groups:  [ { label, value, pct, color } ],     // 参赛组别构成
 *    trend: {
 *      axis:    [ '6.16','6.17','6.18','6.19','6.20','6.21','6.22' ], // X 轴刻度（7 个）
 *      likes:   [ ...7个数字 ],                     // 近 7 天每日点赞
 *      comments:[ ...7个数字 ]                      // 近 7 天每日评论
 *    },
 *    topWorks:  [ { title, author, school, likes, comments } ],  // 热门作品（按点赞降序）
 *    schoolRank:[ { name, score } ],                // 学校参与热度（综合分降序）
 *    wordCloud: [ { text, weight, kind } ],         // 互动热词：weight 1~10；kind: title|theme|comment
 *    feed:      [ { kind, user, work, note, time } ]// 实时动态：kind: like|comment
 *  }
 * -------------------------------------------------------------------------- */

const MOCK_DATA = {
  kpi: {
    works: 235, likes: 18426, comments: 4073, views: 126840, schools: 28,
    likesToday: 1240, commentsToday: 286, viewsToday: 8640
  },
  awards: [
    { label: '入围参展',     value: 112, color: '#1f5346' },
    { label: '二等奖',       value: 66,  color: '#2BB7C4' },
    { label: '一等奖',       value: 30,  color: '#3FE0A0' },
    { label: 'AI二等奖',     value: 13,  color: '#8FD17A' },
    { label: 'AI一等奖',     value: 10,  color: '#F4C95D' },
    { label: '植物插画专项', value: 4,   color: '#FF8E72' }
  ],
  groups: [
    { label: '小学组', value: 168, pct: 71.5, color: '#38E1A3' },
    { label: '初中组', value: 52,  pct: 22.1, color: '#F4C95D' },
    { label: '高中组', value: 15,  pct: 6.4,  color: '#FF8E72' }
  ],
  trend: {
    axis:     ['6.16', '6.17', '6.18', '6.19', '6.20', '6.21', '6.22'],
    likes:    [1820, 1690, 1340, 1510, 1180, 1480, 1020],
    comments: [470, 390, 340, 440, 300, 380, 260]
  },
  topWorks: [
    { title: '《竹子》',              author: '罗喻馨', school: '杨行中心校',        likes: 1284, comments: 312 },
    { title: '《AI绘梦 诗意节气》',   author: '马皖宁', school: '上海大学附属学校',  likes: 1156, comments: 268 },
    { title: '《大寒·立春》',         author: '沈亦舟', school: '宝山区实验小学',    likes: 982,  comments: 197 },
    { title: '《记录我的研究与成长》', author: '朱允和', school: '经纬实验小学',      likes: 864,  comments: 156 },
    { title: '《青竹问雪》',          author: '陈思远', school: '第一中心小学',      likes: 731,  comments: 143 }
  ],
  schoolRank: [
    { name: '宝山区实验小学',              score: 4820 },
    { name: '上海市宝山区杨行中心校',       score: 3960 },
    { name: '上海大学附属学校',            score: 3410 },
    { name: '上海师大附属宝山经纬实验小学', score: 2870 },
    { name: '上海市宝山区第一中心小学',     score: 2240 },
    { name: '罗店中心校',                  score: 1680 }
  ],
  wordCloud: [
    { text: '《竹子》',       weight: 10, kind: 'title' },
    { text: '《AI绘梦》',     weight: 7,  kind: 'title' },
    { text: '《大寒·立春》',  weight: 6,  kind: 'title' },
    { text: '《青竹问雪》',   weight: 5,  kind: 'title' },
    { text: '《记录成长》',   weight: 4,  kind: 'title' },
    { text: '二十四节气',     weight: 9,  kind: 'theme' },
    { text: '国风',          weight: 8,  kind: 'theme' },
    { text: '植物之美',       weight: 7,  kind: 'theme' },
    { text: '节气之美',       weight: 6,  kind: 'theme' },
    { text: '太空竹林',       weight: 4,  kind: 'theme' },
    { text: '春耕',          weight: 5,  kind: 'theme' },
    { text: '梅兰竹菊',       weight: 6,  kind: 'theme' },
    { text: '荷塘清趣',       weight: 3,  kind: 'theme' },
    { text: '芳华',          weight: 4,  kind: 'theme' },
    { text: 'AI创想',        weight: 3,  kind: 'theme' },
    { text: '笔触细腻',       weight: 7,  kind: 'comment' },
    { text: '很有想象力',     weight: 7,  kind: 'comment' },
    { text: '构图有意境',     weight: 6,  kind: 'comment' },
    { text: '创意满分',       weight: 5,  kind: 'comment' },
    { text: '色彩温暖',       weight: 5,  kind: 'comment' },
    { text: '国风韵味',       weight: 4,  kind: 'comment' },
    { text: '画得真好',       weight: 4,  kind: 'comment' },
    { text: '童趣满满',       weight: 3,  kind: 'comment' },
    { text: '治愈',          weight: 4,  kind: 'comment' },
    { text: '想象力',         weight: 5,  kind: 'comment' },
    { text: '细腻动人',       weight: 3,  kind: 'comment' }
  ],
  feed: [
    { kind: 'like',    user: '苏雅南', work: '《竹子》',            note: '',                 time: '刚刚' },
    { kind: 'comment', user: '王老师', work: '《AI绘梦 诗意节气》', note: '构图很有意境',     time: '1分钟前' },
    { kind: 'like',    user: '访客',   work: '《大寒·立春》',       note: '',                 time: '2分钟前' },
    { kind: 'comment', user: '林家长', work: '《记录我的研究与成长》', note: '孩子真棒',      time: '3分钟前' },
    { kind: 'like',    user: '陈思远', work: '《青竹问雪》',         note: '',                 time: '4分钟前' },
    { kind: 'comment', user: '评委',   work: '《竹子》',            note: '笔触细腻自然',     time: '5分钟前' }
  ]
};

/* -----------------------------------------------------------------------------
 *  字段映射 —— 如果你们接口返回的字段名和上面 SHAPE 不同，在这里转换。
 *  示例：把后端的 { total_works, like_count, ... } 映射成本面板需要的结构。
 *  若接口字段已经一致，直接 return raw 即可。
 * -------------------------------------------------------------------------- */
function mapApiResponse(raw) {
  // 示例（按需修改）：
  // return {
  //   kpi: {
  //     works: raw.total_works,
  //     likes: raw.like_count,
  //     comments: raw.comment_count,
  //     views: raw.page_views,
  //     schools: raw.school_count,
  //     likesToday: raw.like_today,
  //     commentsToday: raw.comment_today,
  //     viewsToday: raw.view_today
  //   },
  //   awards: raw.awards,
  //   groups: raw.groups,
  //   trend: raw.trend,
  //   topWorks: raw.hot_works,
  //   schoolRank: raw.school_rank,
  //   wordCloud: raw.keywords,
  //   feed: raw.activities
  // };
  return raw;
}

/* -----------------------------------------------------------------------------
 *  统一入口 —— 面板调用此函数获取数据，无需改动可视化代码。
 * -------------------------------------------------------------------------- */
async function fetchDashboardData() {
  if (USE_MOCK) return MOCK_DATA;
  try {
    const res = await fetch(API_URL, { credentials: 'include' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const raw = await res.json();
    return mapApiResponse(raw);
  } catch (err) {
    console.error('[dashboard] 拉取真实数据失败，回退到示例数据：', err);
    return MOCK_DATA;   // 接口异常时不至于白屏
  }
}

window.DASHBOARD = { fetchDashboardData, REFRESH_MS, USE_MOCK };
