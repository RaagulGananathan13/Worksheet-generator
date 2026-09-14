/* Real browser acceptance checks against a local, isolated test server.
 * Never point this script at production: it creates test accounts/worksheets.
 * Uses the existing generator's installed Puppeteer without editing it.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const puppeteer = require('../../backend/node_modules/puppeteer');
const {spawn, spawnSync} = require('node:child_process');

const root = path.resolve(__dirname, '..');
const base = 'http://127.0.0.1:8017';
const artifacts = path.join(root, 'artifacts', 'browser');
fs.mkdirSync(artifacts, {recursive:true});
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const errors = [];
const click = async (page, selector) => { await page.waitForSelector(selector, {visible:true}); await page.click(selector); };
const api = (page, endpoint) => page.evaluate(async endpoint => {
  const response = await fetch('/api'+endpoint);
  if (!response.ok) throw Error('API '+endpoint+': '+response.status);
  return response.json();
}, endpoint);

async function login(page, username, password) {
  await page.goto(base, {waitUntil:'networkidle0'});
  await page.type('[name=username]', username);
  await page.type('[name=password]', password);
  await click(page, '#auth-form [type=submit]');
  await page.waitForSelector('[data-action=logout]');
}

async function main() {
  try {
    await fetch(base+'/api/health');
    throw Error('Port 8017 is already in use. Stop the previous test server before this test.');
  } catch(error) {
    if(error.message.includes('already in use')) throw error;
  }
  const python = process.platform==='win32' ? path.join(root,'.venv','Scripts','python.exe') : path.join(root,'.venv','bin','python');
  const server = spawn(python,['run.py','--port','8017'],{cwd:root,windowsHide:true,
    env:{...process.env,PYTHONUNBUFFERED:'1',AG_DATA_DIR:path.join(root,'artifacts','browser-runs',String(Date.now())),
      AG_BOOTSTRAP_TOKEN:'local-smoke-setup-not-for-production',AG_SECURE_COOKIES:'0',OCR_MODEL_PATH:'artifacts/intentionally-no-model'}});
  const serverLog=fs.createWriteStream(path.join(artifacts,'server.log'));
  server.stdout.pipe(serverLog);server.stderr.pipe(serverLog);
  for(let attempt=0;attempt<50;attempt++){
    try{const response=await fetch(base+'/api/health');if(response.ok)break;}catch{}
    await delay(200);
  }
  const browser = await puppeteer.launch({headless:true,args:['--no-sandbox']});
  try {
    const teacherContext = await browser.createBrowserContext();
    const teacher = await teacherContext.newPage();
    teacher.on('pageerror', error => errors.push('teacher: '+error.message));
    await teacher.setViewport({width:1440,height:1000,deviceScaleFactor:1});
    await teacher.goto(base, {waitUntil:'networkidle0'});
    const health = await api(teacher,'/health');
    assert.equal(health.setup_required,true,'Use a fresh isolated test database for this script.');
    await teacher.screenshot({path:path.join(artifacts,'01-setup.png'),fullPage:true});
    await teacher.type('[name=token]','local-smoke-setup-not-for-production');
    await teacher.type('[name=name]','Test Teacher');
    await teacher.type('[name=username]','browser.teacher');
    await teacher.type('[name=password]','Local-smoke-password-123');
    await click(teacher,'#auth-form [type=submit]');
    await teacher.waitForSelector('[data-action=import]');
    const session = await api(teacher,'/session');
    const code = session.user.class_code;
    await click(teacher,'[data-action=import]');
    await click(teacher,'[data-action=import-sample][data-file="48544102.pdf"]');
    await teacher.waitForSelector('#keys-confirmed');
    await teacher.screenshot({path:path.join(artifacts,'02-teacher-editor.png'),fullPage:true});
    await click(teacher,'#keys-confirmed');
    await click(teacher,'[data-action=publish-worksheet]');
    if (await teacher.$('dialog[open] [data-action=confirm-dialog]')) await click(teacher,'[data-action=confirm-dialog]');
    await teacher.waitForFunction(async () => {
      const data=await (await fetch('/api/worksheets')).json();return data.worksheets.some(w=>w.published);
    });
    const library=await api(teacher,'/worksheets');
    const worksheet=library.worksheets[0];

    const pupilContext = await browser.createBrowserContext();
    const pupil = await pupilContext.newPage();
    pupil.on('pageerror', error => errors.push('student: '+error.message));
    await pupil.setViewport({width:1024,height:1366,deviceScaleFactor:1,hasTouch:true});
    await pupil.goto(base,{waitUntil:'networkidle0'});
    await click(pupil,'[data-action=auth-register]');
    await pupil.type('[name=name]','Test Student');
    await pupil.type('[name=username]','browser.student');
    await pupil.type('[name=password]','Local-smoke-password-123');
    await pupil.type('[name=class_code]',code);
    await click(pupil,'#auth-form [type=submit]');
    await click(pupil,'[data-action=start-worksheet]');
    await pupil.waitForSelector('#answer-pad');
    const attemptId = await pupil.evaluate(()=>location.hash.split('/')[1]);
    let attempt = await api(pupil,'/attempts/'+attemptId);
    assert(!('expected' in attempt.questions[0]),'Student must not receive answer key');
    const values=['3','7','11','5','13','8','4','10','6','14','9','12','7','14','5'];
    for(let i=0;i<values.length;i++){
      await click(pupil,`[data-action=select-question][data-id="add-${i+1}"]`);
      await click(pupil,'[data-action=mode-type]');
      await pupil.waitForSelector('#typed-answer');
      await pupil.type('#typed-answer',values[i]);
    }
    await click(pupil,'[data-action=select-question][data-id="add-16"]');
    await click(pupil,'[data-action=mode-ink]');
    await pupil.waitForSelector('#answer-pad');
    await pupil.$eval('#answer-pad',canvas=>canvas.scrollIntoView({block:'center'}));
    const box = await (await pupil.$('#answer-pad')).boundingBox();
    const cdp = await pupil.createCDPSession();
    const points = [[.25,.25],[.7,.25],[.6,.45],[.5,.65],[.4,.85]];
    for(let i=0;i<points.length;i++){
      const [x,y]=points[i];
      if(i===0) await cdp.send('Input.dispatchMouseEvent',{type:'mouseMoved',x:box.x+x*box.width,y:box.y+y*box.height,pointerType:'pen'});
      await cdp.send('Input.dispatchMouseEvent',{type:i===0?'mousePressed':'mouseMoved',x:box.x+x*box.width,y:box.y+y*box.height,button:'left',buttons:1,clickCount:i===0?1:0,pointerType:'pen',force:.7});
    }
    await cdp.send('Input.dispatchMouseEvent',{type:'mouseReleased',x:box.x+.4*box.width,y:box.y+.85*box.height,button:'left',buttons:0,clickCount:1,pointerType:'pen'});
    await pupil.waitForFunction(async id=>{
      const data=await(await fetch('/api/attempts/'+id)).json();
      return Object.keys(data.answers).length===16 && data.answers['add-16']?.strokes?.length>0;
    },{timeout:15000},attemptId);
    attempt=await api(pupil,'/attempts/'+attemptId);
    assert(attempt.answers['add-16'].strokes[0].points.some(p=>p.p>.6),'Pen pressure must be preserved');
    assert.equal(attempt.answers['add-1'].text,'3');
    await pupil.screenshot({path:path.join(artifacts,'03-student-tablet.png'),fullPage:true});
    await pupil.reload({waitUntil:'networkidle0'});
    await click(pupil,'[data-action=select-question][data-id="add-16"]');
    await pupil.waitForSelector('#answer-pad');
    assert((await api(pupil,'/attempts/'+attemptId)).answers['add-16'].strokes.length>0,'Ink survives reload');
    await click(pupil,'[data-action=submit-attempt]');
    await click(pupil,'dialog[open] [data-action=confirm-dialog]');
    await pupil.waitForFunction(async id=>{
      const data=await(await fetch('/api/attempts/'+id)).json();return ['review','graded'].includes(data.status);
    },{timeout:150000},attemptId);
    attempt=await api(pupil,'/attempts/'+attemptId);
    assert.equal(attempt.summary.earned,15);
    assert.equal(attempt.summary.pending,1);
    assert.equal(attempt.summary.final,false);
    await pupil.screenshot({path:path.join(artifacts,'04-student-results.png'),fullPage:true});

    await click(teacher,'[data-action=results]');
    await click(teacher,`[data-action=open-attempt][data-id="${attemptId}"]`);
    await click(teacher,'[data-action=select-question][data-id="add-16"]');
    await teacher.waitForSelector('#review-form');
    await teacher.type('#review-mark','0');
    await teacher.type('#review-feedback','Teacher checked the ink: 7 is not 11.');
    await click(teacher,'#review-form [type=submit]');
    await teacher.waitForFunction(async id=>{
      const data=await(await fetch('/api/attempts/'+id)).json();return data.summary.final;
    },{},attemptId);
    attempt=await api(teacher,'/attempts/'+attemptId);
    assert.equal(attempt.summary.percentage,93.75);
    const pdf = await teacher.evaluate(async id=>{
      const response=await fetch('/api/attempts/'+id+'/report.pdf');
      return {status:response.status,type:response.headers.get('content-type'),length:(await response.arrayBuffer()).byteLength};
    },attemptId);
    assert.equal(pdf.status,200);assert(pdf.length>1000);
    await teacher.screenshot({path:path.join(artifacts,'05-teacher-review.png'),fullPage:true});
    // Separate fixture: tablet choices, offline recovery, and optimistic conflicts.
    const counts = await teacher.evaluate(async ()=>{
      const session=await(await fetch('/api/session')).json();
      const headers={'Content-Type':'application/json','X-CSRF-Token':session.csrf_token};
      const worksheet=await(await fetch('/api/samples/import',{method:'POST',headers,body:JSON.stringify({filename:'91903282.pdf'})})).json();
      return (await fetch('/api/worksheets/'+worksheet.id,{method:'PUT',headers,body:JSON.stringify({title:worksheet.title,questions:worksheet.questions,revision:worksheet.revision,published:true,keys_confirmed:true})})).json();
    });
    await click(pupil,'[data-action=library]');
    await click(pupil,`[data-action=start-worksheet][data-id="${counts.id}"]`);
    await pupil.waitForSelector('.choice-options [data-value="7"]');
    await pupil.tap('.choice-options [data-value="7"]');
    const countsAttemptId=await pupil.evaluate(()=>location.hash.split('/')[1]);
    await pupil.waitForFunction(async id=>(await(await fetch('/api/attempts/'+id)).json()).answers['count-1']?.text==='7',{},countsAttemptId);
    await click(pupil,'[data-action=select-question][data-id="flower-1"]');
    await click(pupil,'[data-action=mode-type]');
    await pupil.setOfflineMode(true);
    await pupil.type('#typed-answer','2');
    await pupil.waitForFunction(()=>document.querySelector('#save-status').textContent.includes('device'));
    const localCopy=await pupil.evaluate(()=>Object.keys(localStorage).some(key=>{
      try{const item=JSON.parse(localStorage.getItem(key));return item.unsaved&&item.answers?.['flower-1']?.text==='2';}catch{return false;}
    }));
    assert(localCopy,'Offline edits must have a local recovery copy');
    await pupil.setOfflineMode(false);
    await pupil.waitForFunction(async id=>(await(await fetch('/api/attempts/'+id)).json()).answers['flower-1']?.text==='2',{timeout:15000},countsAttemptId);
    // Save externally first, then try to overwrite from stale UI state.
    await pupil.evaluate(async id=>{
      const session=await(await fetch('/api/session')).json();
      const attempt=await(await fetch('/api/attempts/'+id)).json();
      attempt.answers['flower-2']={text:'5',strokes:[]};
      await fetch('/api/attempts/'+id+'/answers',{method:'PUT',headers:{'Content-Type':'application/json','X-CSRF-Token':session.csrf_token},body:JSON.stringify({version:attempt.version,answers:attempt.answers})});
    },countsAttemptId);
    await pupil.type('#typed-answer','0');
    await pupil.waitForFunction(()=>document.querySelector('#save-status').textContent.includes('conflict'),{timeout:10000});
    assert.equal((await api(pupil,'/attempts/'+countsAttemptId)).answers['flower-1'].text,'2','Stale browser must not overwrite saved answers');
    await pupil.screenshot({path:path.join(artifacts,'07-version-conflict.png'),fullPage:true});
    await click(pupil,'[data-action=reload-attempt]');
    await click(pupil,'dialog[open] [data-action=confirm-dialog]');
    await pupil.waitForFunction(()=>!document.querySelector('#save-status').textContent.includes('conflict'));
    await click(pupil,'[data-action=library]');
    await click(pupil,`[data-action=start-worksheet][data-id="${worksheet.id}"]`);
    await pupil.setViewport({width:390,height:844,deviceScaleFactor:1,hasTouch:true});
    await pupil.reload({waitUntil:'networkidle0'});
    await pupil.screenshot({path:path.join(artifacts,'06-phone-layout.png'),fullPage:true});
    const overflow=await pupil.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2);
    assert.equal(overflow,false,'Phone layout must not overflow horizontally');
    await click(pupil,'[data-action=results]');
    await pupil.waitForSelector(`[data-action=open-attempt][data-id="${attemptId}"]`);
    await pupil.evaluate(id=>{
      const realFetch=window.fetch.bind(window);
      window.fetch=async(...args)=>{
        const response=await realFetch(...args);
        if(String(args[0])==='/api/attempts/'+id && !window.__heldOnce){
          window.__heldOnce=true;
          return new Promise(resolve=>{window.__releaseOldResponse=()=>resolve(response);});
        }
        return response;
      };
    },attemptId);
    await click(pupil,`[data-action=open-attempt][data-id="${attemptId}"]`);
    await pupil.waitForFunction(()=>typeof window.__releaseOldResponse==='function');
    await click(pupil,'[data-action=logout]');
    await pupil.waitForSelector('#auth-form');
    await pupil.evaluate(()=>window.__releaseOldResponse());
    await delay(300);
    assert(await pupil.$('#auth-form'),'Late authenticated response must not restore the signed-out worksheet');
    assert.equal(await pupil.$('.workbench'),null);
    assert.equal((await api(pupil,'/session')).user,null);
    assert.deepEqual(errors,[],'Browser JavaScript errors');
    const report={passed:true,checks:['teacher setup','sample import and publish','student registration','15 typed answers','pen pressure and autosave','reload persistence','answer-key privacy','pending handwriting review','teacher final mark','PDF report','tablet choice tap','offline local recovery and reconnect','version conflict refuses overwrite','phone width','logout','late authenticated response rejected after logout'],finalScore:attempt.summary,browserErrors:errors};
    fs.writeFileSync(path.join(artifacts,'result.json'),JSON.stringify(report,null,2));
    console.log(JSON.stringify(report,null,2));
  } finally {
    await browser.close();
    if(process.platform==='win32') spawnSync('taskkill',['/PID',String(server.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});
    else server.kill('SIGTERM');
    serverLog.end();
  }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
