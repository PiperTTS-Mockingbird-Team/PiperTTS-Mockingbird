let started = false;

export function initOrbs(config = {}) {
  if (started) return;
  const canvas = document.getElementById('c');
  if (!canvas) return;
  started = true;

  const {
    initialParticles = 6000,
    maxParticles = 12000,
    fpsTarget = 58,
  } = config;

  const ctx = canvas.getContext('2d', { alpha: false });

  // --- Performance-first knobs ---
  const DPR_CAP = 1.15;                        // cap device pixel ratio
  const GRID_SCALE = 10;                       // px per velocity cell (was 6)

  let DPR = Math.max(1, Math.min(DPR_CAP, window.devicePixelRatio || 1));

  // Pre-rendered glow sprite (drawn once, blitted many times)
  let glowSprite, glowSize;
  function makeGlowSprite() {
    glowSize = Math.round(3.0 * DPR);          // base radius in device px
    const s = glowSize * 2 + 1;
    const off = document.createElement('canvas');
    off.width = off.height = s;
    const gctx = off.getContext('2d');
    const grd = gctx.createRadialGradient(glowSize, glowSize, 0, glowSize, glowSize, glowSize);
    grd.addColorStop(0.00, 'rgba(180, 0, 255, 0.55)');
    grd.addColorStop(0.50, 'rgba(140, 0, 200, 0.22)');
    grd.addColorStop(1.00, 'rgba(40, 0, 70, 0.00)');
    gctx.fillStyle = grd;
    gctx.fillRect(0, 0, s, s);
    glowSprite = off;
  }

  // Resize
  function resize() {
    const w = Math.floor(innerWidth * DPR);
    const h = Math.floor(innerHeight * DPR);
    canvas.width = w; canvas.height = h;
    canvas.style.width = innerWidth + 'px';
    canvas.style.height = innerHeight + 'px';
    flow.resize(w, h);
  }
  window.addEventListener('resize', resize);

  // Simple flow field (coarser + fewer smooth passes)
  const flow = (() => {
    let W = 0, H = 0, cols = 0, rows = 0, scale = GRID_SCALE;
    let vx, vy;
    const idx = (x,y) => x + y * cols;
    function resize(w,h){
      W=w; H=h; cols = Math.ceil(W/scale); rows = Math.ceil(H/scale);
      vx = new Float32Array(cols*rows);
      vy = new Float32Array(cols*rows);
    }
    function addVelocity(px,py,fx,fy,radiusPx){
      const r = Math.max(4,(radiusPx||40)*DPR)/scale;
      const cx = px/scale, cy = py/scale; const r2 = r*r;
      const minx = Math.max(0, (cx - r)|0), maxx = Math.min(cols-1, (cx + r)|0);
      const miny = Math.max(0, (cy - r)|0), maxy = Math.min(rows-1, (cy + r)|0);
      for(let y=miny;y<=maxy;y++){
        for(let x=minx;x<=maxx;x++){
          const dx = x-cx, dy=y-cy; const d2 = dx*dx+dy*dy; if(d2>r2) continue;
          const fall = Math.exp(-d2/(r2*0.75)); const i=idx(x,y);
          vx[i]+=fx*fall; vy[i]+=fy*fall;
        }
      }
    }
    function step(){
      const visc=0.95; const smoothIters=1; // fewer iters
      for(let k=0;k<smoothIters;k++){
        for(let y=1;y<rows-1;y++){
          for(let x=1;x<cols-1;x++){
            const i=idx(x,y), il=idx(x-1,y), ir=idx(x+1,y), iu=idx(x,y-1), id=idx(x,y+1);
            vx[i] = (vx[i] + 0.15*(vx[il]+vx[ir]+vx[iu]+vx[id]-4*vx[i]));
            vy[i] = (vy[i] + 0.15*(vy[il]+vy[ir]+vy[iu]+vy[id]-4*vy[i]));
          }
        }
      }
      for(let i=0;i<vx.length;i++){ vx[i]*=visc; vy[i]*=visc; }
    }
    function velocityAt(px,py){
      const gx = Math.max(0, Math.min(cols-1.001, px/scale));
      const gy = Math.max(0, Math.min(rows-1.001, py/scale));
      const x0 = gx|0, y0 = gy|0, x1 = Math.min(x0+1, cols-1), y1 = Math.min(y0+1, rows-1);
      const sx = gx-x0, sy = gy-y0; const i00=idx(x0,y0), i10=idx(x1,y0), i01=idx(x0,y1), i11=idx(x1,y1);
      const vx0=vx[i00]*(1-sx)+vx[i10]*sx, vx1=vx[i01]*(1-sx)+vx[i11]*sx;
      const vy0=vy[i00]*(1-sx)+vy[i10]*sx, vy1=vy[i01]*(1-sx)+vy[i11]*sx;
      return {x:vx0*(1-sy)+vx1*sy, y:vy0*(1-sy)+vy1*sy};
    }
    return { resize, addVelocity, step, velocityAt };
  })();

  // Particles (draw via sprite blits instead of per-particle gradients)
  const particles = (() => {
    let PCOUNT = initialParticles;
    let pts, life;
    function alloc(){
      pts = new Float32Array(PCOUNT*4);
      life= new Float32Array(PCOUNT);
    }
    function reset(i){
      pts[i]   = Math.random()*canvas.width;
      pts[i+1] = Math.random()*canvas.height;
      pts[i+2] = (Math.random()-0.5)*0.15;
      pts[i+3] = (Math.random()-0.5)*0.15;
      life[i>>2] = Math.random()*0.2;
    }
    function init(){ alloc(); for(let p=0;p<PCOUNT;p++) reset(p<<2); }
    function step(dt){
      const drag=0.986, decay=0.987;
      for(let k=0,j=0;k<PCOUNT;k++,j+=4){
        const x=pts[j], y=pts[j+1];
        const v=flow.velocityAt(x,y);
        pts[j+2] = pts[j+2]*drag + v.x*0.9;
        pts[j+3] = pts[j+3]*drag + v.y*0.9;
        pts[j]   = x + pts[j+2]*dt;
        pts[j+1] = y + pts[j+3]*dt;
        if(pts[j]<0) pts[j]+=canvas.width; else if(pts[j]>=canvas.width) pts[j]-=canvas.width;
        if(pts[j+1]<0) pts[j+1]+=canvas.height; else if(pts[j+1]>=canvas.height) pts[j+1]-=canvas.height;
        life[k]*=decay;
      }
    }
    function excite(px,py,strength){
      const r = Math.max(canvas.width, canvas.height)*0.12; const r2=r*r; const s=Math.min(1.4, Math.max(0.25, strength||1));
      for(let k=0,j=0;k<PCOUNT;k++,j+=4){
        const dx=pts[j]-px, dy=pts[j+1]-py; const d2=dx*dx+dy*dy; if(d2<r2){ life[k]=Math.min(1, life[k]+Math.exp(-d2/(r2*0.6))*s); }
      }
    }
    function draw(ctx){
      ctx.globalCompositeOperation='lighter';
      for(let k=0,j=0;k<PCOUNT;k++,j+=4){
        const a=life[k]; if(a<0.02) continue;
        const x=pts[j], y=pts[j+1];
        ctx.globalAlpha = Math.min(0.9, a*0.9);
        const r = glowSize*(1 + a*2.2);
        ctx.drawImage(glowSprite, x - r, y - r, r*2, r*2);
      }
      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation='source-over';
    }
    function adaptParticles(target){
      target = Math.max(1500, Math.min(maxParticles, target|0));
      if(target === PCOUNT) return;
      PCOUNT = target; alloc(); init();
    }
    return { init, step, draw, excite, adaptParticles };
  })();

  // Input
  const pointer = { x:0, y:0, vx:0, vy:0, speed:0 };
  function setPointer(e){
    const rect = canvas.getBoundingClientRect();
    const x = ((e.touches? e.touches[0].clientX : e.clientX) - rect.left) * DPR;
    const y = ((e.touches? e.touches[0].clientY : e.clientY) - rect.top) * DPR;
    pointer.vx = x - pointer.x; pointer.vy = y - pointer.y;
    pointer.speed = Math.hypot(pointer.vx, pointer.vy);
    pointer.x = x; pointer.y = y;
  }
  window.addEventListener('mousemove', e=>{ setPointer(e); flow.addVelocity(pointer.x,pointer.y,pointer.vx*0.12,pointer.vy*0.12,60); particles.excite(pointer.x,pointer.y, Math.min(1.1, 0.2 + pointer.speed/60)); });
  window.addEventListener('touchmove', e=>{ e.preventDefault(); setPointer(e); flow.addVelocity(pointer.x,pointer.y,pointer.vx*0.12,pointer.vy*0.12,70); particles.excite(pointer.x,pointer.y, Math.min(1.2, 0.25 + pointer.speed/40)); }, { passive:false });

  // Adaptive performance controller
  let last = performance.now();
  let fpsEMA = 60; // exponential moving average
  function frame(t){
    const dtms = Math.min(33, t-last); last=t; const dt = dtms*0.06;
    const isDark = matchMedia && matchMedia('(prefers-color-scheme: dark)').matches;
    ctx.fillStyle = isDark ? 'rgba(0,0,0,0.28)' : 'rgba(248,250,252,0.28)';
    ctx.fillRect(0,0,canvas.width,canvas.height);

    flow.step();
    particles.step(dt);
    particles.draw(ctx);

    // Adapt: if fps < drop threshold, drop particles; if > fpsTarget, add a bit back
    const fps = 1000/Math.max(1, dtms); fpsEMA = fpsEMA*0.9 + fps*0.1;
    if ((performance.now()|0)%500 < 16) { // check ~2x/sec
      if (fpsEMA < fpsTarget - 13) {
        particles.adaptParticles((initialParticles * 0.75)|0);
        DPR = Math.max(1, DPR*0.95); // nudge DPR down
        resize(); makeGlowSprite();
      } else if (fpsEMA > fpsTarget && DPR < DPR_CAP){
        // small quality nudge up
        DPR = Math.min(DPR_CAP, DPR*1.02);
        resize(); makeGlowSprite();
      }
    }
    requestAnimationFrame(frame);
  }

  // Boot
  makeGlowSprite();
  resize();
  particles.init();
  // Seed a small swirl
  const cx = () => canvas.width*0.5, cy = () => canvas.height*0.5;
  for (let a=0; a<Math.PI*2; a+=Math.PI/24){
    const r = Math.min(canvas.width, canvas.height)*0.25;
    const x = cx() + Math.cos(a)*r; const y = cy() + Math.sin(a)*r;
    const fx = -Math.sin(a)*2.0, fy = Math.cos(a)*2.0;
    flow.addVelocity(x,y,fx,fy,35);
  }

  requestAnimationFrame(frame);
}

