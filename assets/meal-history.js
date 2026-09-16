(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const campus = new URLSearchParams(location.search).get('campus') || sessionStorage.getItem('bs_campus') || 'benbu';
  let data, list, generation = 0, photoUrl, largeUrl, localUrl, busy = false, page = 0;
  function message(text, error = false) { $('status').textContent = text; $('status').className = error ? 'error' : ''; }
  function url(path) { return path + (path.includes('?') ? '&' : '?') + 'campus=' + encodeURIComponent(campus); }
  async function request(path, options = {}, blob = false) {
    const token = sessionStorage.getItem('bs_session_token');
    const response = await fetch(url(path), {...options, headers: {...options.headers, ...(token ? {Authorization: 'Bearer ' + token} : {})}, cache: 'no-store'});
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.error || ({403:'登录已失效或没有此操作权限，请返回登录页重新登录。',503:'餐食历史功能正在准备中，请稍后重试。',413:'图片过大，请压缩至20MB以内。'}[response.status]) || `请求失败（${response.status}），请稍后重试。`);
    }
    return blob ? response.blob() : response.json();
  }
  function path() { return `/api/meal-history/${$('semester').value}/${$('week').value}`; }
  function term(s) { return `${s.slice(0,4)}—${Number(s.slice(0,4))+1}学年 第${s.endsWith('1')?'一':'二'}学期`; }
  function timestamp(s) { return s ? new Date(s.replace(' ','T')+'Z').toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})+'（北京时间）' : ''; }
  function cells(row, values) { values.forEach(value => { const cell = document.createElement('td'); cell.textContent = value ?? ''; row.append(cell); }); }
  function clearUpload() {
    $('file').value = ''; $('replace').checked = false; $('localPreview').hidden = true;
    if (localUrl) URL.revokeObjectURL(localUrl); localUrl = null;
  }
  async function loadWeeks() {
    const current = ++generation; $('content').hidden = true; $('uploadPanel').hidden = true;
    message('正在加载周次…');
    const result = await request('/api/meal-history' + ($('semester').value ? '?semester=' + $('semester').value : ''));
    if (current !== generation) return;
    list = result;
    $('semester').replaceChildren(...list.semesters.map(s => new Option(term(s), s, false, s === list.semester)));
    $('week').replaceChildren(...list.weeks.map(w => new Option(`第${w.week}周 · ${w.dateStart} 至 ${w.dateEnd}${w.photo?' · 有实拍':''}`, w.week)));
    if (!list.weeks.length) { message('此学期暂无已发布的菜单记录。'); return; }
    await loadDetail();
  }
  async function loadDetail() {
    const current = ++generation;
    clearUpload(); $('content').hidden = true; $('uploadPanel').hidden = true; $('photo').hidden = true;
    message('正在加载记录…');
    const result = await request(path());
    if (current !== generation) return;
    data = result;
    $('content').hidden = false; $('uploadPanel').hidden = !list.canManage;
    $('uploadTarget').textContent = `当前上传目标：${({benbu:'本部',baolin:'宝林分校',luojing:'罗泾'})[list.campus] || ''} · ${term(data.semester)} · 第${data.week}周`;
    $('replaceLabel').hidden = !data.photo;
    const source = {deadline:'截止归档',backfill:'历史回填（由现存数据重建）',revision:'人工修正版'};
    $('archiveStatus').textContent = data.version ? `${source[data.source] || data.source} · 第${data.version}版 · ${timestamp(data.archivedAt)}${data.reason ? ' · 原因：'+data.reason : ''}` : '尚未归档：当前仅展示菜单，选餐人数和明细将在截止归档后展示。';
    const warnings = [...data.warnings];
    if (data.source === 'backfill') warnings.push('回填无法还原已被覆盖或删除的历史记录；不等同于当时的原始快照。');
    if (data.changed) warnings.push('归档后实时数据发生变化，请总务核对。当前显示的仍是已归档版本。');
    if (data.detailRestricted) warnings.push('往学期的班级成员可能变化，班主任请联系总务查询往学期明细。');
    $('warnings').hidden = !warnings.length; $('warnings').textContent = warnings.join('\n');
    $('scope').textContent = `统计范围：${data.scope}。人数为选餐记录数，不代表实际到校用餐人数。`;
    $('days').replaceChildren(...data.days.map(day => {
      const row = document.createElement('tr');
      const plans = data.mealPlans.filter(p => p.plan_date === day.plan_date).map(p => `${p.plan_type}餐：${p.plan_name}`).join('；');
      const normal = day.service_status === 'normal';
      cells(row, [day.plan_date, normal ? (plans || '历史菜单文本未留存') : '不供餐：'+(day.service_note || ''), data.version && !data.detailRestricted ? day.A : '—', data.version && !data.detailRestricted ? day.B : '—']);
      return row;
    }));
    page = 0; renderChoices();
    $('details').hidden = !data.version || data.detailRestricted;
    $('export').hidden = !data.canExport;
    $('revisionPanel').hidden = !data.canRearchive || (!!data.version && !data.changed);
    $('photoStatus').textContent = data.photo ? `第${data.photo.version}版 · 发布于${timestamp(data.photo.published_at)} · 点击照片查看大图` : '此周暂未上传餐食实拍。';
    if (photoUrl) URL.revokeObjectURL(photoUrl); photoUrl = null;
    message('');
    if (data.photo) {
      const blob = await request(`/api/meal-photos/${data.photo.id}/file?preview=1`, {}, true);
      if (current !== generation) return;
      photoUrl = URL.createObjectURL(blob); $('photo').src = photoUrl; $('photo').hidden = false;
    }
  }
  function renderChoices() {
    $('choices').replaceChildren(...data.choices.slice(page*100,(page+1)*100).map(p => { const row = document.createElement('tr'); cells(row,[`${p.grade || ''} ${p.class_name || ''}`,p.name,p.plan_date,p.choice]);return row; }));
    $('pageInfo').textContent = `共${data.choices.length}条 · 第${page+1}/${Math.max(1,Math.ceil(data.choices.length/100))}页`;
    $('previousPage').disabled = page === 0;
    $('nextPage').disabled = (page+1)*100 >= data.choices.length;
  }
  $('previousPage').onclick = () => { page--; renderChoices(); };
  $('nextPage').onclick = () => { page++; renderChoices(); };
  async function action(button, fn) {
    if (busy) return; busy = true; button.disabled = true; $('semester').disabled = true; $('week').disabled = true;
    try { await fn(); } catch (error) { message(error.message, true); }
    finally { busy = false; button.disabled = false; $('semester').disabled = false; $('week').disabled = false; }
  }
  $('semester').onchange = () => loadWeeks().catch(e => message(e.message,true));
  $('week').onchange = () => loadDetail().catch(e => message(e.message,true));
  $('file').onchange = () => {
    if (localUrl) URL.revokeObjectURL(localUrl);
    const file = $('file').files[0]; $('localPreview').hidden = !file;
    if (file) { localUrl = URL.createObjectURL(file); $('localPreview').src = localUrl; }
  };
  $('uploadForm').onsubmit = event => {
    event.preventDefault();
    action($('uploadButton'), async () => {
      if (!data || !list.canManage) return;
      if (data.photo && !$('replace').checked) throw new Error('请勾选确认替换，并核对周次。');
      const file = $('file').files[0];
      if (!file || file.size > 20*1024*1024) throw new Error('请选择20MB以内的图片。');
      const form = new FormData(); form.append('image',file); form.append('version',data.photo?.version || 0);
      message('正在上传、校验并生成预览，请勿关闭页面…');
      await request(path()+'/photos',{method:'POST',body:form});
      await loadDetail(); message('餐食照片已发布。');
    });
  };
  $('revisionForm').onsubmit = event => {
    event.preventDefault(); action($('revisionButton'), async () => {
      await request(path()+'/rearchive',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reason:$('reason').value,version:data.version})});
      await loadDetail(); message('归档已完成，旧版本仍然保留。');
    });
  };
  $('export').onclick = () => action($('export'),async () => {
    const blob = await request(path()+'/export.xlsx',{},true); const objectUrl = URL.createObjectURL(blob);
    const anchor = document.createElement('a'); anchor.href=objectUrl; anchor.download=`餐食历史_${data.semester}_W${data.week}.xlsx`; anchor.click();
    setTimeout(() => URL.revokeObjectURL(objectUrl),60000);
    message('已发起下载；如钉钉未接收文件，请在电脑浏览器打开本页面下载。');
  });
  $('photo').onclick = () => action($('photo'),async () => {
    const current = generation; const blob = await request(`/api/meal-photos/${data.photo.id}/file`,{},true);
    if (current !== generation) return;
    if (largeUrl) URL.revokeObjectURL(largeUrl); largeUrl=URL.createObjectURL(blob);
    $('largePhoto').src=largeUrl; $('zoom').hidden=false; $('closeZoom').focus();
  });
  $('photo').onkeydown = e => { if(e.key==='Enter') $('photo').click(); };
  $('closeZoom').onclick = () => { $('zoom').hidden=true; $('photo').focus(); };
  document.addEventListener('keydown',e => { if(e.key==='Escape') $('closeZoom').click(); });
  $('back').href=url('/island-health.html');
  const start = () => loadWeeks().catch(e => message(e.message,true));
  if(window.UserAuth) UserAuth.ready(start); else start();
})();
