/* ═══════════════════════════════════════════════════════════
   钉钉 H5 微应用启动脚本
   引入(放在 <head> 末尾):
     <script>window.BS_DINGTALK_CORP_ID = '__INJECT_CORP_ID__';</script>
     <script src="//g.alicdn.com/dingding/dingtalk-jsapi/2.13.42/dingtalk.open.js"></script>
     <script src="assets/dingtalk-bootstrap.js"></script>

   生效条件:页面被钉钉 WebView 加载(navigator.userAgent 含 'DingTalk')

   职责:
     1. 拉 authCode → POST /api/auth/dingtalk → 存 sessionToken(3 次重试)
     2. 让 /api/* 请求自动带 Authorization: Bearer <sessionToken>
     3. 把页面 <title> 同步到钉钉顶栏
     4. 注入 H5 兼容补丁 CSS(字号 / 横向滑动 / 禁默认下拉刷新)
     5. 失败时给一个友好的提示页(非控制台日志)
   ═══════════════════════════════════════════════════════════ */
(function(global){
  'use strict';

  var inDingTalk = /DingTalk/i.test(navigator.userAgent);
  // ===== 1. H5 兼容补丁 CSS(钉钉 webview 内 + 普通浏览器均生效)=====
  (function injectCss(){
    var style = document.createElement('style');
    style.id = 'bs-dingtalk-fix';
    style.textContent = [
      'html{-webkit-text-size-adjust:100%;text-size-adjust:100%}',
      'body{overscroll-behavior-y:contain}',
      '.gallery,.stage,.scroll-x{touch-action:pan-x pan-y}',
      // 钉钉自带导航条 → 让自定义返回按钮在 webview 内隐藏(以免重复)
      'body.in-dingtalk .back-btn{display:none !important}',
      // iOS 安全区
      '@supports(padding:max(0px)){.topbar{padding-top:max(0px,env(safe-area-inset-top))}}',
    ].join('\n');
    (document.head || document.documentElement).appendChild(style);
    if(inDingTalk) document.documentElement.classList.add('in-dingtalk');
  })();

  // ===== 2. 全局劫持 fetch 自动带 Bearer 头 =====
  (function patchFetch(){
    if(global.__bs_fetch_patched) return;
    global.__bs_fetch_patched = true;
    var orig = global.fetch.bind(global);
    global.fetch = function(input, init){
      init = init || {};
      try {
        var url = typeof input === 'string' ? input : (input && input.url) || '';
        // 只给同源 /api/* 注入,避免泄露给第三方
        if(/^\/api\//.test(url) || /^(?:https?:)?\/\/[^/]+\/api\//i.test(url)){
          var token = sessionStorage.getItem('bs_session_token');
          if(token){
            init.headers = new Headers(init.headers || {});
            if(!init.headers.has('Authorization')){
              init.headers.set('Authorization', 'Bearer ' + token);
            }
          }
        }
      } catch(e){ /* swallow */ }
      return orig(input, init);
    };
  })();

  if(!inDingTalk) return;            // 普通浏览器到此为止(只享受 fetch 补丁)
  if(typeof dd === 'undefined') return;

  // ===== 3. 钉钉自定义顶栏:同步页面标题 =====
  function syncTitle(){
    try {
      var title = document.title || '宝山学习群岛';
      // 只取 · 前的核心标题,避免顶栏过长
      var core = title.split(/[·|]/)[0].trim();
      if(dd.biz && dd.biz.navigation && dd.biz.navigation.setTitle){
        dd.biz.navigation.setTitle({title: core});
      }
    } catch(e){ /* ignore */ }
  }

  // ===== 4. 失败页 =====
  function showFailScreen(msg, retry){
    if(document.getElementById('bs-dt-fail')) return;
    var overlay = document.createElement('div');
    overlay.id = 'bs-dt-fail';
    overlay.style.cssText = 'position:fixed;inset:0;z-index:9999;background:rgba(20,30,40,.92);color:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:24px;font-family:inherit;text-align:center;backdrop-filter:blur(6px)';
    overlay.innerHTML = ''
      + '<div style="font-size:64px;margin-bottom:18px">⚠️</div>'
      + '<div style="font-size:18px;font-weight:800;letter-spacing:1px;margin-bottom:10px">钉钉身份校验失败</div>'
      + '<div style="font-size:13px;opacity:.8;line-height:1.7;max-width:420px;margin-bottom:24px">' + msg + '</div>'
      + '<div style="display:flex;gap:12px;flex-wrap:wrap;justify-content:center">'
      + '<button id="bs-dt-retry" style="padding:10px 28px;border-radius:24px;background:#FFD86A;color:#5C3D17;font-weight:800;border:none;font-size:14px;letter-spacing:1px;cursor:pointer">重试</button>'
      + '<button id="bs-dt-manual" style="padding:10px 28px;border-radius:24px;background:transparent;color:#fff;font-weight:700;border:1.5px solid rgba(255,255,255,.4);font-size:13px;cursor:pointer">手动登录</button>'
      + '</div>';
    document.body.appendChild(overlay);
    document.getElementById('bs-dt-retry').onclick = function(){
      overlay.remove();
      retry();
    };
    document.getElementById('bs-dt-manual').onclick = function(){
      overlay.remove();
      window.dispatchEvent(new CustomEvent('bs:logged-in', {detail:{manualFallback:true}}));
    };
  }

  // ===== 5. authCode → sessionToken,3 次重试 =====
  var corpId = global.BS_DINGTALK_CORP_ID || '';
  var maxRetry = 3;
  function requestAuth(attempt){
    // 钉钉内：检查页面版本，若不一致则强制重登
    var cachedToken = sessionStorage.getItem('bs_session_token');
    var pageVer = global.BS_PAGE_VER || '0';
    var storedVer = sessionStorage.getItem('bs_page_ver') || '';
    if(cachedToken && pageVer === storedVer && pageVer !== '0'){
      syncTitle();
      return;
    }
    attempt = attempt || 1;
    var doExchange = function(authCode) {
      fetch('/api/auth/dingtalk', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({authCode: authCode, campus: (global.BS_CAMPUS_ID || '')})
      }).then(function(r){ return r.json().then(function(d){ return {status:r.status, data:d}; }); })
        .then(function(res){
          var data = res.data;
          if(res.status === 200 && data && data.sessionToken){
            sessionStorage.setItem('bs_session_token', data.sessionToken);
            sessionStorage.setItem('bs_page_ver', global.BS_PAGE_VER || '0');  // 记录页面版本
            if(data.user){
              sessionStorage.setItem('bs_user_nick', data.user.nick || '');
              sessionStorage.setItem('bs_user_avatar', data.user.avatarUrl || '');
              sessionStorage.setItem('bs_dingtalk_unionid', data.user.unionId || '');
            }
            global.dispatchEvent(new CustomEvent('bs:logged-in', {detail: data.user || {}}));
            syncTitle();
          } else if(attempt < maxRetry){
            setTimeout(function(){ requestAuth(attempt + 1); }, 1000 * attempt);
          } else {
            var msg = (data && data.error) || ('HTTP ' + res.status);
            showFailScreen('原因:' + msg + ' · 已重试 ' + maxRetry + ' 次', function(){ requestAuth(1); });
          }
        })
        .catch(function(e){
          if(attempt < maxRetry){
            setTimeout(function(){ requestAuth(attempt + 1); }, 1000 * attempt);
          } else {
            showFailScreen('网络异常:' + (e && e.message || e), function(){ requestAuth(1); });
          }
        });
    };
    // 钉钉免登：各校区写死自己的 corpId（通过 BS_DINGTALK_CORP_ID 注入）
    var params = corpId ? {corpId: corpId} : {};
    dd.getAuthCode(params).then(function(result) {
      var code = result.code || result.authCode || '';
      try { console.log('[BS] requestAuthCode OK corpId=' + corpId + ' code_len=' + code.length); } catch(_){}
      doExchange(code);
    }).catch(function(err){
      if(attempt < maxRetry){
        setTimeout(function(){ requestAuth(attempt + 1); }, 1000 * attempt);
      } else {
        var errInfo = '';
        try {
          var keys = [];
          for(var k in err){ if(err.hasOwnProperty(k)) keys.push(k+'='+JSON.stringify(err[k])); }
          if(keys.length === 0) errInfo = JSON.stringify(err);
          else errInfo = keys.join(' | ');
        } catch(_){ errInfo = String(err); }
        fetch('/api/auth/diag', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
          error: errInfo, errorMessage: err && err.errorMessage, errorCode: err && err.errorCode,
          campus: global.BS_CAMPUS_ID || '', corpId: corpId, ua: navigator.userAgent.substring(0, 200), attempt: attempt
        })}).catch(function(){});
        showFailScreen('钉钉JSAPI拒绝('+attempt+'): ' + errInfo, function(){ requestAuth(1); });
      }
    });
  }

  dd.ready(function(){
    requestAuth(1);
  });
  dd.error(function(err){
    // 不弹失败页(钉钉自己有错就有错),只记一笔
    try { console.warn('[dd.error]', err); } catch(_){}
  });
})(window);
