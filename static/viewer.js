(function () {
  'use strict';

  /* ── État GL ── */
  var gl = null, prog, posBuf, normBuf, numVerts = 0;
  var rotX = 0.4, rotY = 0, dist = 3.5;
  var drag = null, pinch = null;

  /* ── Affiche un statut texte dans le canvas (avant init GL) ── */
  function setStatus(msg) {
    var el = document.getElementById('viewer-status');
    if (el) el.textContent = msg;
  }

  /* ── Matrices 4×4 column-major ── */
  function M4() { return new Float32Array(16); }
  function ident(m) { m.fill(0); m[0]=m[5]=m[10]=m[15]=1; return m; }

  function mul4(a, b) {
    var o=M4(), i, j, k, s;
    for (i=0;i<4;i++) for (j=0;j<4;j++) {
      s=0; for(k=0;k<4;k++) s+=a[k*4+i]*b[j*4+k];
      o[j*4+i]=s;
    }
    return o;
  }

  function perspective(fov, asp, n, f) {
    var m=M4(), t=1/Math.tan(fov*0.5);
    m.fill(0); m[0]=t/asp; m[5]=t;
    m[10]=(f+n)/(n-f); m[11]=-1; m[14]=2*f*n/(n-f);
    return m;
  }

  function rotMat(rx, ry) {
    var cx=Math.cos(rx),sx=Math.sin(rx),cy=Math.cos(ry),sy=Math.sin(ry);
    var m=M4();
    m[0]=cy;      m[4]=0;  m[8]=sy;      m[12]=0;
    m[1]=sx*sy;   m[5]=cx; m[9]=-sx*cy;  m[13]=0;
    m[2]=-cx*sy;  m[6]=sx; m[10]=cx*cy;  m[14]=0;
    m[3]=0;       m[7]=0;  m[11]=0;      m[15]=1;
    return m;
  }

  /* ── Parseur STL binaire ── */
  function parseSTL(ab) {
    var dv=new DataView(ab), i, v, o, vo, p;
    if (ab.byteLength < 84) return null;
    var n=dv.getUint32(80, true);
    if (ab.byteLength < 84+n*50) return null;

    var pos=new Float32Array(n*9), norm=new Float32Array(n*9);
    var mi=[1e9,1e9,1e9], ma=[-1e9,-1e9,-1e9];
    var nx, ny, nz, x, y, z;

    for (i=0; i<n; i++) {
      o=84+i*50;
      nx=dv.getFloat32(o,true); ny=dv.getFloat32(o+4,true); nz=dv.getFloat32(o+8,true);
      for (v=0; v<3; v++) {
        vo=o+12+v*12; p=i*9+v*3;
        x=dv.getFloat32(vo,true); y=dv.getFloat32(vo+4,true); z=dv.getFloat32(vo+8,true);
        pos[p]=x; pos[p+1]=y; pos[p+2]=z;
        norm[p]=nx; norm[p+1]=ny; norm[p+2]=nz;
        if(x<mi[0])mi[0]=x; if(x>ma[0])ma[0]=x;
        if(y<mi[1])mi[1]=y; if(y>ma[1])ma[1]=y;
        if(z<mi[2])mi[2]=z; if(z>ma[2])ma[2]=z;
      }
    }
    var cx=(mi[0]+ma[0])/2, cy=(mi[1]+ma[1])/2, cz=(mi[2]+ma[2])/2;
    var sc=2/Math.max(ma[0]-mi[0], ma[1]-mi[1], ma[2]-mi[2], 1e-6);
    for (i=0; i<pos.length; i+=3) {
      pos[i]=(pos[i]-cx)*sc; pos[i+1]=(pos[i+1]-cy)*sc; pos[i+2]=(pos[i+2]-cz)*sc;
    }
    return { pos:pos, norm:norm, count:n };
  }

  /* ── Shaders GLSL ── */
  var VERT =
    'precision highp float;'+
    'attribute vec3 aP;attribute vec3 aN;uniform mat4 uMVP;varying vec3 vN;'+
    'void main(){gl_Position=uMVP*vec4(aP,1.0);vN=aN;}';
  var FRAG =
    'precision mediump float;varying vec3 vN;'+
    'void main(){'+
    '  vec3 n=normalize(vN);'+
    '  float d=max(dot(n,normalize(vec3(1.0,2.0,2.5))),0.0)*.72'+
    '          +max(dot(n,normalize(vec3(-1.5,-1.0,-1.5))),0.0)*.15+.18;'+
    '  gl_FragColor=vec4(vec3(.82,.82,.85)*d,1.0);}';

  /* ── Init WebGL ── */
  function compileShader(type, src) {
    var s=gl.createShader(type);
    gl.shaderSource(s,src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
      setStatus('Erreur shader: '+gl.getShaderInfoLog(s));
    }
    return s;
  }

  function initGL(canvas) {
    setStatus('Initialisation WebGL...');
    gl = canvas.getContext('webgl', {antialias:false})
      || canvas.getContext('experimental-webgl', {antialias:false});
    if (!gl) { setStatus('WebGL non disponible sur ce navigateur.'); return false; }

    prog=gl.createProgram();
    gl.attachShader(prog, compileShader(gl.VERTEX_SHADER,   VERT));
    gl.attachShader(prog, compileShader(gl.FRAGMENT_SHADER, FRAG));
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      setStatus('Erreur link: '+gl.getProgramInfoLog(prog)); return false;
    }
    gl.useProgram(prog);

    posBuf=gl.createBuffer(); normBuf=gl.createBuffer();
    gl.enable(gl.DEPTH_TEST);
    gl.clearColor(0.067,0.094,0.153,1);
    setStatus('');
    return true;
  }

  function bindBuf(buf, name) {
    var loc=gl.getAttribLocation(prog, name);
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 3, gl.FLOAT, false, 0, 0);
  }

  function upload(data) {
    gl.bindBuffer(gl.ARRAY_BUFFER, posBuf);
    gl.bufferData(gl.ARRAY_BUFFER, data.pos,  gl.STATIC_DRAW);
    gl.bindBuffer(gl.ARRAY_BUFFER, normBuf);
    gl.bufferData(gl.ARRAY_BUFFER, data.norm, gl.STATIC_DRAW);
    numVerts = data.count * 3;
    setStatus('');
  }

  /* ── Rendu ── */
  function render() {
    if (!gl) return;
    var c=gl.canvas;
    gl.viewport(0, 0, c.width, c.height);
    gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
    if (!numVerts) return;

    var rot=rotMat(rotX, rotY);
    var t=ident(M4()); t[14]=-dist;
    var view=mul4(t, rot);
    var mvp=mul4(perspective(Math.PI/4, c.width/c.height, 0.01, 1e4), view);

    gl.uniformMatrix4fv(gl.getUniformLocation(prog,'uMVP'), false, mvp);
    bindBuf(posBuf,  'aP');
    bindBuf(normBuf, 'aN');
    gl.drawArrays(gl.TRIANGLES, 0, numVerts);
  }

  function loop() { requestAnimationFrame(loop); render(); }

  /* ── Contrôles ── */
  function attachControls(canvas) {
    canvas.addEventListener('mousedown', function(e){ drag={x:e.clientX,y:e.clientY}; });
    window.addEventListener('mousemove', function(e){
      if (!drag) return;
      rotY+=(e.clientX-drag.x)*.008; rotX+=(e.clientY-drag.y)*.008;
      drag={x:e.clientX,y:e.clientY};
    });
    window.addEventListener('mouseup', function(){ drag=null; });
    canvas.addEventListener('wheel', function(e){
      e.preventDefault(); dist=Math.max(0.5,dist+e.deltaY*.005);
    },{passive:false});

    canvas.addEventListener('touchstart', function(e){
      e.preventDefault();
      if (e.touches.length===1) {
        drag={x:e.touches[0].clientX,y:e.touches[0].clientY};
      } else if (e.touches.length===2) {
        pinch={d:Math.hypot(e.touches[0].clientX-e.touches[1].clientX,
                             e.touches[0].clientY-e.touches[1].clientY), d0:dist};
        drag=null;
      }
    },{passive:false});
    canvas.addEventListener('touchmove', function(e){
      e.preventDefault();
      if (e.touches.length===1&&drag) {
        rotY+=(e.touches[0].clientX-drag.x)*.012;
        rotX+=(e.touches[0].clientY-drag.y)*.012;
        drag={x:e.touches[0].clientX,y:e.touches[0].clientY};
      } else if (e.touches.length===2&&pinch) {
        var d=Math.hypot(e.touches[0].clientX-e.touches[1].clientX,
                         e.touches[0].clientY-e.touches[1].clientY);
        dist=Math.max(0.5,pinch.d0*(pinch.d/d));
      }
    },{passive:false});
    canvas.addEventListener('touchend', function(){ drag=null; pinch=null; });
  }

  /* ── Taille canvas : calcul explicite, pas via getBoundingClientRect ── */
  function fitCanvas() {
    var canvas=document.getElementById('viewer-canvas');
    if (!canvas) return;
    var hint = document.querySelector('.viewer-hint');
    var hintH = hint ? hint.offsetHeight : 40;
    var w = window.innerWidth;
    var h = window.innerHeight - hintH - 48; /* -48 pour la barre de fermeture */
    /* Sur desktop, le container fait 88vw × 82vh */
    var container = document.querySelector('.viewer-container');
    if (container && container.clientWidth > 0) {
      w = container.clientWidth;
      h = container.clientHeight - hintH;
    }
    canvas.width  = Math.max(w, 1);
    canvas.height = Math.max(h, 1);
    if (gl) gl.viewport(0, 0, canvas.width, canvas.height);
  }
  window.addEventListener('resize', fitCanvas);

  /* ── API publique ── */
  window.openViewer = function() {
    document.getElementById('viewer-modal').classList.remove('hidden');
    /* Double rAF : garantit que le navigateur a peint le layout avant d'init GL */
    requestAnimationFrame(function() {
      requestAnimationFrame(function() {
        var canvas=document.getElementById('viewer-canvas');
        fitCanvas();
        if (!gl) {
          if (!initGL(canvas)) return;
          attachControls(canvas);
          loop();
        }
        if (window._stlViewUrl) {
          numVerts=0;
          setStatus('Chargement du modèle...');
          fetch(window._stlViewUrl)
            .then(function(r){
              if (!r.ok) throw new Error('HTTP '+r.status);
              return r.arrayBuffer();
            })
            .then(function(ab){
              setStatus('Traitement...');
              var data=parseSTL(ab);
              if (data) { dist=3.5; rotX=0.4; rotY=0; upload(data); }
              else setStatus('Erreur: fichier STL invalide.');
            })
            .catch(function(e){ setStatus('Erreur: '+e.message); });
        }
      });
    });
  };

  window.closeViewer = function() {
    document.getElementById('viewer-modal').classList.add('hidden');
  };

})();
