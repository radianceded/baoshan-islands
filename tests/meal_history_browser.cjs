// Mocked API browser smoke: no production data, credentials or writes.
const {chromium} = require('playwright');
const fs = require('fs');
const path = require('path');
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({headless:true,channel:'msedge'});
  for (const manager of [true,false]) {
    const page = await browser.newPage({viewport:{width:390,height:844}});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/*',async route=>{
      const url=new URL(route.request().url());
      if(url.pathname==='/meal-history.html') return route.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(__dirname,'../meal-history.html'),'utf8')});
      if(url.pathname==='/assets/meal-history.js')return route.fulfill({contentType:'text/javascript',body:fs.readFileSync(path.join(__dirname,'../assets/meal-history.js'),'utf8')});
      if(url.pathname==='/assets/user-auth.js')return route.fulfill({contentType:'text/javascript',body:'window.UserAuth={ready:fn=>fn()};'});
      if(url.pathname==='/api/meal-history')return route.fulfill({json:{semester:'2026s1',semesters:['2026s1'],canManage:manager,weeks:[{week:2,dateStart:'2026-09-07',dateEnd:'2026-09-13'}]}});
      if(url.pathname==='/api/meal-history/2026s1/2')return route.fulfill({json:{semester:'2026s1',week:2,version:1,source:'backfill',archivedAt:'2026-09-14 07:00:00',photo:null,warnings:[],changed:false,canExport:manager,canRearchive:false,scope:manager?'本校区':'自己的孩子',days:[{plan_date:'2026-09-07',service_status:'normal',A:1,B:0}],mealPlans:[{plan_date:'2026-09-07',plan_type:'A',plan_name:'米饭、青菜'}],choices:[{grade:'三年级',class_name:'2班',name:'测试学生',plan_date:'2026-09-07',choice:'A'}]}});
      return route.fulfill({body:'',contentType:'text/javascript'});
    });
    await page.goto('http://meal-history.test/meal-history.html?campus=benbu');
    await page.locator('#content').waitFor({state:'visible'});
    assert.equal(await page.locator('#uploadPanel').isVisible(),manager);
    assert.equal(await page.locator('#export').isVisible(),manager);
    assert.match(await page.locator('#days').textContent(),/米饭、青菜/);
    await page.locator('summary').click();
    assert.match(await page.locator('#choices').textContent(),/测试学生/);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    assert.deepEqual(errors,[]);
    await page.screenshot({path:path.join(__dirname,manager?'meal-history-manager.png':'meal-history-parent.png'),fullPage:true});
    console.log(`${manager?'manager':'parent'} mobile smoke passed`);
    await page.close();
  }
  await browser.close();
})().catch(e=>{console.error(e);process.exit(1);});
