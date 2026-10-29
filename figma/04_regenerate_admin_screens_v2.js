// 05 관리자 웹 와이어프레임 섹션을 삭제하고 v2(멀티 소스 · 환율 자동 · 배송 프로필) 기준 8화면으로 다시 만든다.
// use_figma(code) 또는 Scripter로 실행. 02_wireframes_source_and_mapping.js 를 대체한다 (둘 다 돌리지 말 것).
const FAM='Noto Sans KR';
const F=s=>({family:FAM,style:s});
await Promise.all(['Regular','Medium','Bold'].map(s=>figma.loadFontAsync(F(s))));
const page=await figma.getNodeByIdAsync('112:2');
await figma.setCurrentPageAsync(page);
const removed=[];
for(const c of [...page.children]){if(c.type==='SECTION'&&c.name.startsWith('05 ')){removed.push(c.id);c.remove();}}
const hex=h=>{const n=parseInt(h.slice(1),16);return{r:((n>>16)&255)/255,g:((n>>8)&255)/255,b:(n&255)/255}};
const solid=(h,o)=>{const p={type:'SOLID',color:hex(h)};if(o!==undefined)p.opacity=o;return p};
function text(str,o={}){const {size=14,style='Regular',color='#1F1F1F',w,align='LEFT',lh}=o;const t=figma.createText();t.fontName=F(style);t.characters=str;t.fontSize=size;t.fills=[solid(color)];if(lh)t.lineHeight={unit:'PIXELS',value:lh};t.textAlignHorizontal=align;if(w){t.resize(w,10);t.textAutoResize='HEIGHT';}return t;}
function label(parent,str,x,y,o={}){const t=text(str,o);t.x=x;t.y=y;parent.appendChild(t);return t;}
function box(parent,o){const {x,y,w,h,fill='#FFFFFF',stroke='#D9D9D9',sw=1,r=8,name='box'}=o;const f=figma.createFrame();f.name=name;f.resize(w,h);f.x=x;f.y=y;f.fills=fill?[solid(fill)]:[];f.strokes=stroke?[solid(stroke)]:[];f.strokeWeight=sw;f.cornerRadius=r;f.clipsContent=false;parent.appendChild(f);return f;}
const S=figma.createSection();S.name='05 관리자 웹 와이어프레임 (v2)';S.x=0;S.y=2400;S.resizeWithoutConstraints(15700,1200);S.fills=[solid('#F7F7F5')];page.appendChild(S);
label(S,'05 관리자 웹 와이어프레임 (1440 × 1000, 로우파이) · v2 멀티 소스',40,32,{size:28,style:'Bold'});
label(S,'좌측 메뉴 11개 · 모든 목록에 소스 축 · 환율은 자동 수집(조회만) · 배송 프로필은 경로별 · AI 제공자·예산·스케줄·스토리지는 시스템 설정 · 설정 변경은 다음 배치부터 적용',40,78,{size:14,color:'#555555'});
const SX=i=>80+i*1560;
const MENU=['대시보드','소스 관리','카테고리 매핑','수집 카테고리','제외 규칙','비용 설정','매칭 설정','콘텐츠 설정','상품 목록','실행 로그','시스템 설정'];
function screen(x,title,active,isNew){label(S,title+(isNew?'  (v2 신규)':''),x,124,{size:16,style:'Bold',color:isNew?'#C05621':'#333333'});const f=box(S,{x,y:156,w:1440,h:1000,fill:'#F7F8FA',stroke:'#B0B0B0',r:0,name:'화면 · '+title});f.clipsContent=true;const sb=box(f,{x:0,y:0,w:220,h:1000,fill:'#1F2933',stroke:null,r:0,name:'사이드바'});label(sb,'auto-store 관리자',20,22,{size:16,style:'Bold',color:'#FFFFFF'});MENU.forEach((m,i)=>{const y=80+i*40;const on=Array.isArray(active)?active.includes(i):i===active;if(on)box(sb,{x:12,y:y-8,w:196,h:34,fill:'#2B6CB0',stroke:null,r:6,name:'active'});label(sb,m,28,y,{size:14,style:on?'Bold':'Regular',color:on?'#FFFFFF':'#CBD2D9'});});label(sb,'admin · 로그아웃',20,960,{size:12,color:'#9AA5B1'});const tb=box(f,{x:220,y:0,w:1220,h:56,fill:'#FFFFFF',stroke:'#E0E0E0',r:0,name:'상단바'});label(tb,title,24,16,{size:18,style:'Bold'});label(tb,'마지막 배치  2026-10-29 02:00 · 소스 5개 중 4개 정상 · 환율 09:00 갱신 · 다음 알림 08:00',640,19,{size:12,color:'#666666'});return f;}
function table(parent,x,y,cols,rows,rowH=38){const w=cols.reduce((a,c)=>a+c[1],0);const t=box(parent,{x,y,w,h:rowH*(rows.length+1),fill:'#FFFFFF',stroke:'#D0D0D0',r:6,name:'표'});t.clipsContent=true;const hd=box(t,{x:0,y:0,w,h:rowH,fill:'#F2F4F7',stroke:null,r:0,name:'머리글'});let cx=0;cols.forEach(c=>{label(hd,c[0],cx+12,11,{size:12,style:'Bold',color:'#444444'});cx+=c[1];});rows.forEach((r,ri)=>{const ry=rowH*(ri+1);if(ri>0)box(t,{x:0,y:ry,w,h:1,fill:'#E8E8E8',stroke:null,r:0,name:'구분선'});let cx=0;r.forEach((cell,ci)=>{if(cell==='ON'||cell==='OFF')toggle(t,cx+12,ry+9,cell==='ON');else if(cell==='[img]')box(t,{x:cx+12,y:ry+5,w:28,h:28,fill:'#E2E8F0',stroke:null,r:4,name:'썸네일'});else if(typeof cell==='string'&&cell.startsWith('[')&&cell.endsWith(']'))label(t,cell.slice(1,-1),cx+12,ry+11,{size:12,style:'Medium',color:'#2B6CB0'});else if(typeof cell==='string'&&cell.startsWith('!'))label(t,cell.slice(1),cx+12,ry+11,{size:12,style:'Medium',color:'#C05621'});else if(typeof cell==='string'&&cell.startsWith('+'))label(t,cell.slice(1),cx+12,ry+11,{size:12,style:'Medium',color:'#2F855A'});else label(t,String(cell),cx+12,ry+11,{size:12,color:'#222222'});cx+=cols[ci][1];});});return t;}
function input(parent,x,y,w,lab,val,o={}){label(parent,lab,x,y,{size:12,color:'#555555'});const b=box(parent,{x,y:y+20,w,h:36,fill:o.ro?'#F2F4F7':'#FFFFFF',stroke:'#B8B8B8',r:6,name:'입력 '+lab});label(b,val,12,9,{size:13,color:o.ph?'#999999':'#222222'});if(o.unit)label(b,o.unit,w-44,9,{size:12,color:'#777777'});if(o.select)label(b,'▾',w-24,8,{size:13,color:'#555555'});return b;}
function btn(parent,x,y,lab,kind='primary',w){const ww=w||lab.length*14+36;const b=box(parent,{x,y,w:ww,h:36,fill:kind==='primary'?'#2B6CB0':kind==='danger'?'#C53030':kind==='success'?'#2F855A':'#FFFFFF',stroke:kind==='ghost'?'#B8B8B8':null,r:6,name:'버튼 '+lab});label(b,lab,0,9,{size:13,style:'Medium',color:kind==='ghost'?'#333333':'#FFFFFF',w:ww,align:'CENTER'});return b;}
function kpi(parent,x,y,w,lab,val,color){const b=box(parent,{x,y,w,h:90,fill:'#FFFFFF',stroke:'#D0D0D0',r:8,name:'지표 '+lab});label(b,lab,16,14,{size:12,color:'#666666'});label(b,val,16,40,{size:26,style:'Bold',color:color||'#1F1F1F'});return b;}
function panel(parent,x,y,w,h,title){const p=box(parent,{x,y,w,h,fill:'#FFFFFF',stroke:'#D0D0D0',r:8,name:title});p.clipsContent=true;label(p,title,16,14,{size:14,style:'Bold'});return p;}
function toggle(parent,x,y,on){const b=box(parent,{x,y,w:36,h:20,fill:on?'#2F855A':'#C4C4C4',stroke:null,r:10,name:on?'켬':'끔'});box(b,{x:on?18:2,y:2,w:16,h:16,fill:'#FFFFFF',stroke:null,r:8,name:'손잡이'});return b;}
function radio(parent,x,y,lab,on){box(parent,{x,y,w:16,h:16,fill:on?'#2B6CB0':'#FFFFFF',stroke:on?'#2B6CB0':'#888888',r:8,name:on?'선택':'미선택'});if(on)box(parent,{x:x+5,y:y+5,w:6,h:6,fill:'#FFFFFF',stroke:null,r:3,name:'점'});label(parent,lab,x+24,y-2,{size:13,color:'#222222'});}
function note(parent,x,y,w,str,h=58){const b=box(parent,{x,y,w,h,fill:'#FFFBE6',stroke:'#E0C76A',r:6,name:'안내'});label(b,str,14,10,{size:12,color:'#5A4A00',w:w-28,lh:18});return b;}
function tab(parent,x,y,lab,on){const b=box(parent,{x,y,w:lab.length*14+40,h:36,fill:on?'#FFFFFF':'#EEF0F4',stroke:on?'#2B6CB0':'#D0D0D0',r:6,name:'탭 '+lab});label(b,lab,0,9,{size:13,style:on?'Bold':'Regular',color:on?'#2B6CB0':'#555555',w:b.width,align:'CENTER'});return b;}
const created=[];

// 1 로그인
label(S,'로그인',SX(0),124,{size:16,style:'Bold',color:'#333333'});
const lg=box(S,{x:SX(0),y:156,w:1440,h:1000,fill:'#EEF0F4',stroke:'#B0B0B0',r:0,name:'화면 · 로그인'});
const lc=box(lg,{x:520,y:320,w:400,h:330,fill:'#FFFFFF',stroke:'#D0D0D0',r:12,name:'로그인 카드'});
label(lc,'auto-store 관리자',24,28,{size:22,style:'Bold'});label(lc,'해외 도매 → 네이버 구매대행 보조 시스템',24,62,{size:12,color:'#666666'});
input(lc,24,100,352,'아이디','admin');input(lc,24,170,352,'비밀번호','••••••••');btn(lc,24,246,'로그인','primary',352);
label(lc,'계정은 .env의 ADMIN_USER / ADMIN_PASSWORD · 로컬 전용',24,300,{size:11,color:'#999999'});

// 2 대시보드
let f=screen(SX(1),'대시보드',0);created.push(f.id);
[['오늘 수집 (5개 소스)','612'],['후보 (마진율 ≥ 30%)','11'],['1차 승인 대기','8','#B7791F'],['카테고리 확인 대기','7','#B7791F'],['감시 중 · 변동 대기','24 · 3','#B7791F'],['오류 / 차단','1 / 7','#C53030']].forEach((v,i)=>kpi(f,244+i*198,80,184,v[0],v[1],v[2]));
btn(f,244,196,'지금 수집 실행');btn(f,392,196,'알림 다시 보내기','ghost');btn(f,564,196,'보류 상품 다시 알림','ghost');btn(f,754,196,'환율 지금 갱신','ghost');
label(f,'이번 달 API 비용 12,340 / 50,000원 (25%) · LLM: Claude · 이미지: 없음',930,205,{size:12,color:'#666666'});
let p=panel(f,244,252,760,420,'소스별 최근 배치 결과');
table(p,16,44,[['소스',120],['수집',70],['정규화 제외',90],['매칭',70],['후보',60],['차단',60],['소요',80],['상태',178]],[['1688','312','88','140','7','5','48분','+정상'],['타오바오','164','41','66','3','0','31분','+정상'],['NETSEA','96','30','38','1','2','22분','!차단 2회 (계속 진행)'],['슈퍼딜리버리','0','-','-','-','-','-','!로그인 만료 → 건너뜀'],['卸問屋.com (테스트)','40','12','-','-','-','9분','테스트 수집만'],['합계','612','171','244','11','7','1시간 50분','']]);
p=panel(f,1024,252,392,420,'상태별 상품 수');
[['collected',612],['normalized',441],['mapping_pending',7],['filtered_out',171],['matched',244],['below_margin',233],['candidate',11],['approved_1',5],['packaged',1]].forEach((s,i)=>{const y=46+i*38;label(p,s[0],16,y+2,{size:12,color:'#333333'});box(p,{x:150,y,w:Math.max(6,Math.round(s[1]/612*190)),h:20,fill:s[0]==='mapping_pending'?'#F6AD55':'#90CDF4',stroke:null,r:3,name:'막대'});label(p,String(s[1]),350,y+2,{size:12,style:'Bold',color:'#333333'});});
p=panel(f,244,692,1172,284,'오류 · 차단 목록');
table(p,16,44,[['시각',110],['소스',110],['단계',120],['상품 / 대상',360],['내용',300],['작업',120]],[['10-29 02:31','1688','① 수집','6912345001 · 玻璃保温杯','슬라이더 캡차 → 건너뜀','[다음 배치]'],['10-29 02:10','NETSEA','① 수집','검색 "お菓子" 3페이지','차단 2회 → 지연 늘려 계속','[정책 보기]'],['10-29 02:00','슈퍼딜리버리','① 수집','소스 전체','로그인 만료 → 당일 건너뜀','[재로그인]'],['10-28 09:31','타오바오','⑦ 콘텐츠','6912340077','이미지 생성 API 한도 초과','[재시도]']]);

// 3 소스 관리 (신규)
f=screen(SX(2),'소스 관리',1,true);created.push(f.id);
btn(f,244,80,'소스 등록');label(f,'소스 5개 · 정상 3 · 주의 1 · 중지 1 · 테스트 중 1',380,90,{size:12,color:'#666666'});
table(f,244,132,[['사용',50],['소스',120],['국가 · 통화',90],['어댑터',120],['배송 프로필',130],['요청 정책',110],['헬스',160],['작업',60]],[['ON','1688','CN · CNY','내장 (1688)','중국 → 배대지 A','2~6초 · 300건','+정상 · 10-29 02:48','[편집]'],['ON','타오바오','CN · CNY','내장 (taobao)','중국 → 배대지 A','3~8초 · 200건','+정상 · 10-29 02:30','[편집]'],['OFF','알리익스프레스','CN · USD','내장 (aliexpress)','중국 → 배대지 A','3~8초 · 100건','중지 (수동)','[편집]'],['ON','NETSEA','JP · JPY','범용 CSS','일본 → 배대지 B','3~7초 · 150건','!차단 2회 · 10-29 02:10','[편집]'],['ON','슈퍼딜리버리','JP · JPY','범용 CSS','일본 → 배대지 B','4~8초 · 100건','!로그인 만료 → 재로그인','[편집]'],['OFF','卸問屋.com','JP · JPY','LLM 추출','일본 → 배대지 B','5~10초 · 50건','테스트 중 (3페이지)','[편집]']]);
p=panel(f,244,420,840,520,'범용 CSS 셀렉터 · NETSEA');
input(p,16,44,808,'목록 URL 패턴 ({q} 검색어 · {page} 페이지)','https://www.netsea.jp/search/?keyword={q}&page={page}');
input(p,16,114,196,'항목 (list item)','.itemList li');input(p,220,114,196,'제목','.itemName');input(p,424,114,196,'가격','.price .num');input(p,628,114,196,'이미지','img.thumb');
input(p,16,184,196,'링크','a.itemLink');input(p,220,184,196,'다음 페이지','a.pager-next');input(p,424,184,196,'최소수량 (없으면 1)','',{ph:true});input(p,628,184,196,'카테고리 표기 (빵부스러기)','.breadcrumb li:last');
label(p,'상세 페이지',16,254,{size:12,style:'Bold',color:'#333333'});
input(p,16,276,196,'가격','.detailPrice');input(p,220,276,196,'속성표','table.spec tr');input(p,424,276,196,'이미지들','.gallery img');input(p,628,276,196,'옵션 (SKU)','select.variation option');
btn(p,16,350,'1페이지 테스트 수집','ghost');btn(p,196,350,'LLM에게 셀렉터 제안 받기','ghost');btn(p,428,350,'저장','primary',112);
note(p,16,400,808,'테스트 결과 (1페이지 · 40건): 제목 40 · 가격 38 · 이미지 40 · 링크 40 · 최소수량 0 (셀렉터 없음 → 기본 1) · 카테고리 표기 40 ("お菓子" → 표준 "식품 > 과자" 추천). 가격 2건 누락은 "요청 시 견적" 상품.',76);
note(f,244,956,840,'내장 어댑터는 코드와 selectors/<key>.yaml로 관리. 범용 CSS는 이 화면에서 셀렉터만 입력. LLM 추출은 셀렉터 없이 느리게 시작하고 몇 페이지 뒤 셀렉터를 제안받아 범용 CSS로 승격.',40);
p=panel(f,1104,80,312,860,'소스 편집 · NETSEA');
input(p,16,44,280,'이름','NETSEA');input(p,16,114,134,'국가','JP',{select:true});input(p,162,114,134,'통화','JPY',{select:true});
label(p,'어댑터 종류',16,184,{size:12,color:'#555555'});radio(p,16,206,'내장',false);radio(p,96,206,'범용 CSS',true);radio(p,200,206,'LLM 추출',false);
input(p,16,236,280,'base URL','https://www.netsea.jp');
label(p,'로그인',16,306,{size:12,color:'#555555'});btn(p,16,326,'브라우저 열어 로그인','ghost',200);label(p,'프로필 저장됨 10-28 · 사업자 회원',16,370,{size:11,color:'#2F855A'});
input(p,16,400,134,'요청 지연 최소','3',{unit:'초'});input(p,162,400,134,'최대','7',{unit:'초'});
input(p,16,470,134,'하루 수집 상한','150',{unit:'건'});input(p,162,470,134,'연속 차단 허용','3',{unit:'회'});
input(p,16,540,280,'배송 프로필','일본 → 한국 배대지 B',{select:true});
label(p,'사용',16,610,{size:12,color:'#555555'});toggle(p,16,630,true);label(p,'끄면 다음 배치부터 제외',64,630,{size:12,color:'#777777'});
btn(p,16,690,'1페이지 테스트 수집','ghost',200);btn(p,16,736,'저장','primary',130);btn(p,160,736,'삭제','danger',112);
label(p,'헬스: 마지막 성공 10-29 02:10 · 연속 실패 0 · 차단 2회',16,800,{size:11,color:'#777777',w:280,lh:16});

// 4 카테고리 매핑 (신규)
f=screen(SX(3),'카테고리 매핑',2,true);created.push(f.id);
p=panel(f,244,80,340,860,'표준 카테고리');
btn(p,16,40,'추가','ghost',70);btn(p,96,40,'CSV 가져오기','ghost');
table(p,16,90,[['경로',170],['네이버',60],['품목',48],['무게',30]],[['식품 > 과자','5000…','food','300'],['식품 > 음료','5000…','food','500'],['주방 > 텀블러','5000…','일반','0'],['주방 > 식기','5000…','일반','0'],['생활 > 수납','5000…','일반','0'],['반려동물 > 급수기','5000…','일반','0'],['디지털 > 액세서리','5000…','전자','0'],['유아 > 장난감','5000…','아동','0'],['의류 > 양말','5000…','일반','50'],['문구 > 필기구','5000…','일반','0']],34);
note(p,16,480,308,'품목 유형(food · 전자 · 아동 · 화장품)이 목록통관 배제와 KC 대상 판단의 기준. 기본 무게는 무게 누락 시 참고값(0 허용).',76);
label(p,'선택: 식품 > 과자',16,580,{size:12,style:'Bold',color:'#2B6CB0'});
input(p,16,606,308,'네이버 카테고리 코드','50000xxx · 식품>과자/간식',{select:true});input(p,16,676,150,'품목 유형','food',{select:true});input(p,174,676,150,'기본 무게','300',{unit:'g'});
btn(p,16,750,'저장','primary',112);
p=panel(f,604,80,400,860,'별칭 사전 · 식품 > 과자');
table(p,16,44,[['표기',150],['언어',50],['출처',70],['확신',50],['',48]],[['과자','ko','seed','1.00','[×]'],['스넥','ko','manual','1.00','[×]'],['스낵류','ko','llm','0.92','[×]'],['零食','zh','seed','1.00','[×]'],['膨化食品','zh','llm','0.81','[×]'],['休闲食品','zh','llm','0.77','[×]'],['お菓子','ja','seed','1.00','[×]'],['スナック','ja','manual','1.00','[×]'],['駄菓子','ja','llm','0.90','[×]'],['snack','en','seed','1.00','[×]']],34);
input(p,16,440,220,'표기 추가','예: 간식',{ph:true});input(p,244,440,124,'언어','ko',{select:true});btn(p,16,506,'추가','primary',100);
note(p,16,560,368,'소스 카테고리 등록 시 이 사전이 표준 카테고리를 추천한다. 상품 자체의 분류 표기가 사전과 충돌하면 확인 큐로 간다.',58);
label(p,'속성 별칭 (재질)',16,640,{size:12,style:'Bold',color:'#333333'});
table(p,16,662,[['코드',80],['표기 (언어)',288]],[['glass','玻璃 (zh) · ガラス (ja) · 유리 (ko) · glass (en)'],['ceramic','陶瓷 (zh) · 陶器 (ja) · 도자기 (ko)'],['battery','含锂电池 (zh) · リチウム電池 (ja) · 배터리 (ko)']],34);
p=panel(f,1024,80,392,860,'확인 대기 큐 · LLM 제안');
label(p,'대기 7건 · 오늘 승인 3 · 거절 1',16,40,{size:12,color:'#666666'});
[['"驴打滚"','zh · 타오바오 · 상품 6912…','식품 > 떡·전통과자','0.74','상품은 mapping_pending'],['"駄菓子"','ja · NETSEA · 카테고리 등록','식품 > 과자','0.90','승인됨 → 사전 추가'],['"ガラス製"','ja · 재질 · 슈퍼딜리버리','material = glass','0.95','제외 규칙 glass 적용 예정'],['"宠物饮水机"','zh · 1688 · 상품 6913…','반려동물 > 급수기','0.88','상품은 mapping_pending']].forEach((q,i)=>{const y=66+i*190;const c=box(p,{x:16,y,w:360,h:176,fill:i===1?'#F0FFF4':'#FFFFFF',stroke:i===1?'#2F855A':'#D0D0D0',r:8,name:'제안 '+q[0]});label(c,q[0],14,12,{size:14,style:'Bold'});label(c,q[1],14,36,{size:11,color:'#666666'});label(c,'제안: '+q[2]+'  (확신 '+q[3]+')',14,60,{size:12,style:'Medium',color:'#2B6CB0'});label(c,q[4],14,82,{size:11,color:'#999999'});if(i!==1){btn(c,14,118,'승인','success',80);btn(c,102,118,'다른 카테고리','ghost');btn(c,236,118,'거절','ghost',70);}else label(c,'승인 완료 · 10-29 08:40',14,124,{size:12,color:'#2F855A'});});

// 5 수집 카테고리 (소스 축 추가)
f=screen(SX(4),'수집 카테고리',3);created.push(f.id);
btn(f,244,80,'수집 카테고리 추가');input(f,420,62,160,'소스 필터','전체',{select:true});label(f,'총 11개 · 사용 중 9 · 오늘 수집 612건',600,90,{size:12,color:'#666666'});
table(f,244,132,[['사용',50],['소스',100],['사이트 표기',120],['목록 URL',200],['표준 카테고리',150],['페이지',60],['마지막 수집',100],['건수',60]],[['ON','1688','厨房用品','1688.com/…/kitchen','주방 > 식기','3','10-29 02:48','96'],['ON','1688','保温杯','s.1688.com/…keywords=保温杯','주방 > 텀블러','5','10-29 02:20','120'],['ON','타오바오','零食','s.taobao.com/…q=零食','식품 > 과자','3','10-29 02:30','84'],['ON','타오바오','收纳','s.taobao.com/…q=收纳','생활 > 수납','3','10-29 02:15','80'],['ON','NETSEA','お菓子','netsea.jp/search/?keyword=お菓子','식품 > 과자','3','10-29 02:10','56'],['ON','NETSEA','タンブラー','netsea.jp/search/?keyword=タンブラー','주방 > 텀블러','2','10-29 02:05','40'],['OFF','슈퍼딜리버리','雑貨','superdelivery.com/…','생활 > 수납','2','10-27 02:30','-'],['ON','卸問屋.com','駄菓子','…(LLM 추출)','식품 > 과자','1','테스트','40']]);
note(f,244,490,840,'같은 표준 카테고리에 여러 소스의 표기를 붙일 수 있다 (零食 · お菓子 · 駄菓子 → 식품 > 과자). 표준 카테고리의 품목 유형이 food면 목록통관 배제로 자동 제외되므로, 과자류는 "참고 수집"으로만 쓰고 후보에는 오르지 않는다는 점을 등록 시 경고한다.',76);
p=panel(f,1104,80,312,700,'수집 카테고리 편집');
input(p,16,44,280,'소스','NETSEA (JP · 범용 CSS)',{select:true});
input(p,16,114,280,'사이트 표기 (원어)','お菓子');
input(p,16,184,280,'목록 URL','https://www.netsea.jp/search/?keyword=お菓子');
input(p,16,254,280,'표준 카테고리','식품 > 과자',{select:true});
label(p,'별칭 사전 추천: お菓子 → 식품 > 과자 (seed 1.00)',16,316,{size:11,color:'#2F855A',w:280,lh:16});
input(p,16,350,134,'수집 페이지 수','3');input(p,162,350,134,'기본 무게 (표준에서 상속)','300',{unit:'g',ro:true});
label(p,'사용',16,420,{size:12,color:'#555555'});toggle(p,16,440,true);
note(p,16,480,280,'품목 유형 food → 목록통관 배제 품목. 수집은 되지만 ② 정규화에서 자동 제외된다.',58);
btn(p,16,560,'저장','primary',120);btn(p,148,560,'이 카테고리만 테스트','ghost');btn(p,16,610,'삭제','danger',120);

// 6 제외 규칙 (소스별 발견 수)
f=screen(SX(5),'제외 규칙',4);created.push(f.id);
tab(f,244,80,'재질',true);tab(f,330,80,'품목 유형',false);tab(f,452,80,'키워드',false);tab(f,560,80,'브랜드 로고',false);
label(f,'코드 16개 · 제외 적용 5개 · 새로 발견 3개 · 코드는 언어와 무관 (玻璃 = ガラス = 유리 = glass)',710,90,{size:12,color:'#666666'});
table(f,244,136,[['제외',60],['코드',110],['표기 예시 (zh / ja / ko)',260],['발견 소스',150],['발견 상품 수',100],['마지막 발견',100],['상태',110]],[['ON','glass','玻璃 · ガラス · 유리','1688 · NETSEA','53','10-29','적용 중'],['ON','ceramic','陶瓷 · 陶器 · 도자기','1688 · 타오바오','29','10-29','적용 중'],['ON','battery','含锂电池 · リチウム電池','1688 · 슈퍼딜리버리','21','10-29','적용 중'],['ON','liquid','液体 · 液体 · 액체','1688','9','10-28','적용 중'],['ON','magnet','磁铁 · 磁石 · 자석','타오바오','6','10-29','적용 중'],['OFF','marble','大理石','1688','2','10-29','!새로 발견'],['OFF','mirror','镜面 · ミラー','타오바오','3','10-29','!새로 발견'],['OFF','lacquer','漆器 (옻칠)','NETSEA','4','10-29','!새로 발견'],['OFF','wood','木质 · 木製 · 원목','1688 · NETSEA','71','10-29','미적용'],['OFF','stainless','不锈钢 · ステンレス','1688 · 타오바오 · NETSEA','158','10-29','미적용'],['OFF','silicone','硅胶 · シリコン','1688 · 타오바오','112','10-29','미적용']]);
note(f,244,610,890,'새 코드는 ② 정규화에서 처음 나오면 "미적용"으로 자동 추가되고 "새로 발견"으로 표시된다. 체크하면 다음 배치부터 모든 소스에 적용된다. 품목 유형 탭에는 목록통관 배제 품목(식품 · 건강기능식품 · 의약품 · 일부 화장품)과 KC 대상(전자 · 아동용품)이 기본 적용으로 들어 있다.',76);
p=panel(f,244,700,890,240,'브랜드 로고 탭 미리보기 · 비전 LLM 감지 → 자동 제외');
label(p,'자동 제외',16,46,{size:12,color:'#555555'});toggle(p,80,44,true);label(p,'끄면 제외하지 않고 카드에 "브랜드 의심" 경고만 표시',130,46,{size:12,color:'#777777'});
table(p,16,78,[['상품',260],['소스',90],['감지 내용',260],['확신',60],['처리',100],['작업',80]],[['无线蓝牙耳机 (대표 이미지)','타오바오','Apple 로고 · "AirPods" 각인','0.97','brand_detected','[복원]'],['キャラクター弁当箱','NETSEA','산리오 캐릭터','0.93','brand_detected','[복원]'],['运动水杯','1688','로고 유사 문양 (불명확)','0.58','!경고만','[제외]']],36);
p=panel(f,1154,80,262,420,'키워드 직접 추가');
input(p,16,44,230,'키워드 (언어 무관)','예: 브랜드명, 定制, 中古',{ph:true});
label(p,'적용 대상',16,114,{size:12,color:'#555555'});radio(p,16,136,'상품명',true);radio(p,110,136,'속성표',false);
btn(p,16,170,'추가','primary',120);
label(p,'현재 키워드 8개',16,230,{size:12,style:'Bold',color:'#333333'});
['定制 (주문제작)','批发 (도매 전용)','Nike','Disney','散装 (벌크)','礼盒 (선물세트)','中古 (중고 · ja)','二手 (중고 · zh)'].forEach((k,i)=>{const b=box(p,{x:16+(i%2)*118,y:256+Math.floor(i/2)*34,w:110,h:26,fill:'#EEF0F4',stroke:null,r:13,name:'칩'});label(b,k+'  ×',10,5,{size:11,color:'#333333'});});

// 7 비용 · 매칭 · 콘텐츠 설정 (환율 자동 · 배송 프로필)
f=screen(SX(6),'비용 · 매칭 · 콘텐츠 설정',[5,6,7]);created.push(f.id);
p=panel(f,244,80,380,400,'환율 (자동 수집 · 수동 입력 없음)');
table(p,16,44,[['통화',70],['원화',90],['출처',110],['갱신',78]],[['CNY','193.20','수출입은행 API','10-29 09:00'],['JPY (100)','915.40','수출입은행 API','10-29 09:00'],['USD','1,392.00','수출입은행 API','10-29 09:00']],36);
btn(p,16,200,'지금 갱신','ghost',120);label(p,'다음 자동 갱신 10-30 01:50 (배치 직전)',148,210,{size:11,color:'#777777'});
note(p,16,250,348,'출처 우선순위: 1 한국수출입은행 환율 API → 2 네이버 금융 환율 페이지 크롤링 → 3 마지막 성공값. 48시간 넘게 갱신 실패면 원가에 rate_stale 플래그가 붙고 알림 카드에 경고가 표시된다.',94);
p=panel(f,244,500,380,430,'통관 · 수수료 · 기준');
input(p,16,44,170,'목록통관 한도','150',{unit:'USD'});input(p,206,44,158,'통관 경고 구간','130',{unit:'USD'});
input(p,16,114,170,'관세율 (한도 초과 시)','8',{unit:'%'});input(p,206,114,158,'부가세율','10',{unit:'%'});
input(p,16,184,170,'네이버 판매 수수료','5.5',{unit:'%'});input(p,206,184,158,'결제 수수료','2.0',{unit:'%'});
input(p,16,254,170,'목표 마진율 (알림 기준)','30',{unit:'%'});input(p,206,254,158,'소스 기본 수집 상한','300',{unit:'건'});
note(p,16,330,348,'마진율 = (국내 비교가 − 총원가) ÷ 국내 비교가. 총원가 = 소스가×최소수량 + 현지 배송 + 배대지(배송 프로필) + 관부가세 + 수수료.',76);
p=panel(f,644,80,380,850,'배송 프로필 (경로별)');
tab(p,16,40,'중국 → 배대지 A',true);tab(p,166,40,'일본 → 배대지 B',false);btn(p,316,40,'+','ghost',48);
input(p,16,90,170,'통화','CNY',{select:true});input(p,206,90,158,'현지 배송비 기본','8',{unit:'CNY'});
input(p,16,160,170,'평균 배송일 (고지문)','7~14',{unit:'일'});input(p,206,160,158,'사용 소스','1688 · 타오바오 · 알리',{ro:true});
label(p,'요율표 (무게 구간 · 원)',16,230,{size:12,style:'Bold',color:'#333333'});
table(p,16,252,[['구간 (kg 이하)',170],['요금 (원)',178]],[['0.5','6,000'],['1.0','7,500'],['1.5','9,000'],['2.0','10,500'],['3.0','13,500'],['5.0','19,500'],['10.0','34,500']],34);
btn(p,16,540,'구간 추가','ghost',120);btn(p,148,540,'CSV 가져오기','ghost');
label(p,'부피 무게',16,600,{size:12,color:'#555555'});radio(p,16,622,'사용 안 함',true);radio(p,130,622,'가로×세로×높이 ÷ 6000',false);
note(p,16,660,348,'무게 0(미확인) 상품은 배대지 요금 0으로 계산되고 알림에 경고가 붙는다. 소스는 프로필 하나를 가리키며, 프로필을 바꾸면 그 소스 상품의 원가가 다음 배치에서 재계산된다.',76);
p=panel(f,1044,80,372,460,'매칭 · 후보 설정');
label(p,'정확도 프리셋',16,44,{size:12,color:'#555555'});radio(p,16,66,'엄격 (0.90)',false);radio(p,130,66,'보통 (0.80)',true);radio(p,244,66,'넓게 (0.70)',false);
input(p,16,96,160,'정확 매칭 임계값','0.80');input(p,196,96,160,'유사 매칭 하한','0.50');
label(p,'국내 비교 가격 방식',16,166,{size:12,color:'#555555'});radio(p,16,188,'상위 N개 평균',true);radio(p,150,188,'중앙값',false);radio(p,250,188,'최저가',false);
input(p,16,216,160,'상위 N','10');input(p,196,216,160,'검색어 생성 수','3');
input(p,16,286,160,'하루 후보 수 (카드 발송)','10',{unit:'건'});input(p,196,286,160,'후보 정렬','마진율 높은 순',{select:true});
input(p,16,356,160,'소스 간 그룹 임계값','0.85');input(p,196,356,160,'그룹 기준','최저 총원가',{select:true});
label(p,'프리셋을 바꾸면 임계값이 채워지고, 직접 수정하면 "사용자 지정"이 된다. 기준을 넘은 후보가 N건보다 많으면 나머지는 상품 목록에 "후보(미전송)"으로 남는다.',16,420,{size:11,color:'#777777',w:340,lh:16});
p=panel(f,1044,560,372,370,'콘텐츠 설정');
label(p,'이미지 생성 모드',16,44,{size:12,color:'#555555'});radio(p,16,66,'A · 중국어/일본어 제거만',false);radio(p,16,92,'B · 제거 + 한국어 삽입',false);radio(p,16,118,'C · 상품 사진 소재로 전체 재구성',true);
input(p,16,150,160,'상품명 최대 길이','50',{unit:'자'});input(p,196,150,160,'상세 이미지 최대 장수','12',{unit:'장'});
label(p,'구매대행 고지문 템플릿 ({country} {lead_days} 변수)',16,220,{size:12,color:'#555555'});
const ta=box(p,{x:16,y:240,w:340,h:110,fill:'#FFFFFF',stroke:'#B8B8B8',r:6,name:'텍스트영역'});label(ta,'본 상품은 {country}에서 발송되는 해외 구매대행 상품입니다. 통관을 위해 개인통관고유부호가 필요하며, 배송 기간은 영업일 기준 {lead_days}일입니다. 단순 변심 반품 시 해외 반송 비용이 발생합니다…',12,10,{size:12,color:'#333333',w:316,lh:18});
const sv=box(f,{x:220,y:944,w:1220,h:56,fill:'#FFFFFF',stroke:'#E0E0E0',r:0,name:'저장 바'});label(sv,'변경 사항은 다음 배치부터 적용된다 · 마지막 저장 10-28 21:10',24,19,{size:12,color:'#666666'});btn(sv,1084,10,'저장','primary',112);btn(sv,960,10,'기본값 복원','ghost');

// 8 상품 목록 + 상세 (소스 축 · 그룹 비교)
f=screen(SX(7),'상품 목록',8);created.push(f.id);
tab(f,244,62,'전체',true);tab(f,320,62,'후보',false);tab(f,396,62,'감시 중 (listed) 24',false);
input(f,244,106,120,'소스','전체',{select:true});input(f,376,106,120,'상태','전체',{select:true});input(f,508,106,150,'표준 카테고리','전체',{select:true});input(f,670,106,100,'마진율 ≥','30',{unit:'%'});input(f,782,106,200,'검색','상품명 / 상품 ID',{ph:true});btn(f,994,126,'검색','primary',80);
table(f,244,184,[['',50],['소스',80],['상품명 (한 / 원어)',230],['원가 (통화)',90],['국내 비교가',90],['마진율',60],['매칭',80],['플래그',90],['상태',100],['작업',50]],[['[img]','1688','스테인리스 보온 텀블러 500ml\n不锈钢保温杯 500ml','¥18.5×2','24,900','46%','정확3 유사7','!무게 미확인','approved_1','[상세]'],['[img]','타오바오','스테인리스 보온 텀블러 500ml\n不锈钢保温杯 (그룹 동일)','¥17.9×1','24,900','43%','그룹','그룹 2위','candidate','[상세]'],['[img]','NETSEA','스테인리스 텀블러 500ml\nステンレスタンブラー','¥380×1','24,900','31%','그룹','그룹 3위','candidate','[상세]'],['[img]','타오바오','실리콘 접이식 도시락 2단\n硅胶折叠饭盒','¥12.0×1','18,900','38%','정확1 유사9','','candidate','[상세]'],['[img]','NETSEA','나무 젓가락 세트 10P\n木製箸セット','¥290×1','12,900','28%','유사 6','!참고치','below_margin','[상세]'],['[img]','1688','반려동물 자동 급수기\n宠物自动饮水机','¥45.0×1','39,900','31%','정확2 유사4','!KC 대상','filtered_out','[상세]'],['[img]','1688','접이식 빨래 바구니\n折叠洗衣篮','¥15.5×1','16,900','36%','정확2 유사8','','packaged','[등록 완료]'],['[img]','1688','스테인리스 보온 텀블러 (등록됨)\n스토어 #1234567','¥21.8×2','27,900','12%','감시','!가격 +18%','listed','[결정]'],['[img]','NETSEA','스테인리스 텀블러 (등록됨)\n스토어 #1234570','¥380×1','24,900','31%','감시','!페이지 삭제','listed','[결정]']],56);
label(f,'총 612건 · 1 / 62 페이지   ‹  1  2  3  …  62  ›   ·   "등록 완료" 버튼: 스토어 상품번호와 판매가를 입력하면 listed가 되어 ⑩ 감시 대상에 들어간다',244,704,{size:12,color:'#666666'});
p=panel(f,1164,80,252,900,'상품 상세 · 1688 · 6912345678');
box(p,{x:16,y:44,w:220,h:120,fill:'#E2E8F0',stroke:null,r:8,name:'대표 이미지'});label(p,'대표 이미지 · 상세 9장 보기',16,170,{size:12,color:'#2B6CB0'});
label(p,'스테인리스 보온 텀블러 500ml',16,196,{size:13,style:'Bold',w:220});
label(p,'원가 내역 (CNY 193.20 · 중국 → 배대지 A)',16,236,{size:12,style:'Bold',color:'#333333'});
[['구매원가 ¥18.5 × 2','6,900'],['현지 배송 ¥8','1,550'],['배대지 310g 구간','6,000'],['관부가세 (USD 61 ≤ 150)','0'],['네이버 수수료 5.5%','1,370'],['결제 수수료 2.0%','498'],['총원가','16,318'],['국내 비교가 (상위10 평균)','24,900'],['마진율','34%']].forEach((r,i)=>{const y=258+i*21;const bold=i>=6;label(p,r[0],16,y,{size:11,style:bold?'Bold':'Regular',color:'#333333'});label(p,r[1],166,y,{size:11,style:bold?'Bold':'Regular',color:'#333333',w:70,align:'RIGHT'});});
label(p,'다른 소스 비교 (그룹 0.91)',16,456,{size:12,style:'Bold',color:'#333333'});
[['1688 (기준)','16,318'],['타오바오 ¥17.9 ×1','17,040'],['NETSEA ¥380','21,760']].forEach((r,i)=>{const y=478+i*21;label(p,r[0],16,y,{size:11,color:i===0?'#2F855A':'#333333'});label(p,r[1],166,y,{size:11,color:'#333333',w:70,align:'RIGHT'});});
label(p,'매칭 결과',16,550,{size:12,style:'Bold',color:'#333333'});
[['정확 · 스토어A','23,900'],['정확 · 스토어B','24,500'],['정확 · 스토어C','26,300'],['유사 7건 보기 ▾','']].forEach((r,i)=>{const y=572+i*21;label(p,r[0],16,y,{size:11,color:i===3?'#2B6CB0':'#333333'});label(p,r[1],166,y,{size:11,color:'#333333',w:70,align:'RIGHT'});});
label(p,'승인 · 감시 이력',16,664,{size:12,style:'Bold',color:'#333333'});
label(p,'1차 승인  10-29 08:14 · 2차 승인 10-29 09:40\n등록 완료  10-29 11:00 · 스토어 #1234567 · 23,900원\n감시  10-30 02:40 가격 +18% → 결정 대기',16,686,{size:11,color:'#333333',lh:17});
input(p,16,742,220,'변동 결정','판매가 수정 → 27,900원 제안',{select:true});
btn(p,16,800,'결정 적용','success',104);btn(p,132,800,'지금 점검','ghost',104);
btn(p,16,846,'판매 중지','danger',104);btn(p,132,846,'소스에서 열기','ghost',104);

// 9 시스템 설정 (신규): AI 제공자 · 예산 · 스케줄 · 스토리지 · 텔레그램
f=screen(SX(8),'시스템 설정',10,true);created.push(f.id);
p=panel(f,244,80,380,420,'AI 제공자');
label(p,'텍스트 LLM',16,44,{size:12,style:'Bold',color:'#333333'});
radio(p,16,66,'Claude',true);radio(p,116,66,'Gemini',false);radio(p,216,66,'OpenAI',false);
input(p,16,96,170,'모델','claude-opus-5-5',{select:true});input(p,206,96,158,'API 키','sk-ant-••••••••••••');
btn(p,16,160,'연결 테스트','ghost',110);label(p,'정상 · 10-29 09:02 · 응답 1.2초',136,170,{size:11,color:'#2F855A'});
label(p,'이미지 생성 (모드 C 연출컷)',16,214,{size:12,style:'Bold',color:'#333333'});
radio(p,16,236,'사용 안 함',true);radio(p,116,236,'Gemini',false);radio(p,216,236,'OpenAI',false);
input(p,16,266,170,'모델','',{ph:true,select:true});input(p,206,266,158,'API 키','',{ph:true});
note(p,16,330,348,'키는 .env 또는 이 화면에 입력(암호화 저장). 화면 값이 우선하고, 지우면 .env 값으로 돌아간다. 제공자를 바꾸면 다음 호출부터 적용된다.',72);
p=panel(f,644,80,380,420,'API 예산');
input(p,16,44,170,'월 예산','50,000',{unit:'원'});input(p,206,44,158,'경고 비율','80',{unit:'%'});
label(p,'초과 시 동작',16,114,{size:12,color:'#555555'});radio(p,16,136,'⑦ 콘텐츠 생성 중단 + 알림',true);radio(p,16,160,'경고만 보내고 계속',false);
label(p,'이번 달 사용 (추정)',16,196,{size:12,style:'Bold',color:'#333333'});
box(p,{x:16,y:218,w:348,h:14,fill:'#E2E8F0',stroke:null,r:7,name:'예산 바'});box(p,{x:16,y:218,w:86,h:14,fill:'#2F855A',stroke:null,r:7,name:'사용'});
label(p,'12,340원 / 50,000원 (25%) · 경고선 40,000원',16,238,{size:11,color:'#555555'});
table(p,16,264,[['용도',150],['호출',70],['추정 비용',128]],[['정규화 · 매칭 판정','1,210','7,420원'],['콘텐츠 생성','18','3,960원'],['LLM 추출 어댑터','40','960원'],['이미지 생성','0','0원']],30);
p=panel(f,1044,80,372,420,'배치 스케줄');
input(p,16,44,160,'수집 시작 시각','02:00');input(p,196,44,160,'1차 알림 시각','08:00');
label(p,'실행 요일',16,114,{size:12,color:'#555555'});
['월','화','수','목','금','토','일'].forEach((d,i)=>{const on=true;const b=box(p,{x:16+i*48,y:134,w:40,h:30,fill:on?'#2B6CB0':'#FFFFFF',stroke:on?null:'#B8B8B8',r:6,name:'요일 '+d});label(b,d,0,6,{size:13,style:'Medium',color:on?'#FFFFFF':'#333333',w:40,align:'CENTER'});});
input(p,16,184,160,'환율 갱신','배치 10분 전',{select:true});input(p,196,184,160,'배치 미실행 경고','켬',{select:true});
label(p,'등록 상품 감시 (⑩)',16,250,{size:12,style:'Bold',color:'#333333'});
input(p,16,270,160,'감시 주기','3',{unit:'일마다'});input(p,196,270,160,'가격 변동 임계값','5',{unit:'%'});
label(p,'감시 중 24건 · 마지막 점검 10-30 02:40 · 다음 11-02 · 변동 대기 3건',16,330,{size:11,color:'#777777',w:340,lh:16});
btn(p,16,360,'지금 수집 실행','ghost',110);btn(p,136,360,'지금 알림 발송','ghost',110);btn(p,256,360,'지금 점검','ghost',100);
p=panel(f,244,520,580,410,'이미지 스토리지 · Supabase');
input(p,16,44,548,'프로젝트 URL (SUPABASE_URL)','https://xxxxxxxxxxxx.supabase.co');
input(p,16,114,270,'Service role 키 (SUPABASE_SERVICE_KEY)','eyJ••••••••••••••••');input(p,306,114,258,'버킷 (SUPABASE_BUCKET)','product-images');
input(p,16,184,548,'공개 URL 패턴','https://xxxx.supabase.co/storage/v1/object/public/product-images/{path}',{ro:true});
btn(p,16,250,'연결 테스트 (업로드 · 공개 읽기)','ghost');label(p,'정상 · 버킷 public · 10-29 09:03',270,260,{size:11,color:'#2F855A'});
note(p,16,300,548,'⑨ 패키지 생성 시 상세 이미지를 업로드하고 공개 URL을 엑셀 이미지 칸에 넣는다. 경로는 {YYYY-MM-DD}/{소스}_{상품ID}/{n}.jpg. 로컬 output/에도 사본을 남긴다. 이번 달 업로드 1,240장 · 310MB.',76);
p=panel(f,844,520,572,410,'텔레그램 · 계정');
input(p,16,44,270,'봇 토큰','7123456789:AA••••••••');input(p,306,44,250,'chat_id','123456789');
btn(p,16,110,'테스트 메시지 보내기','ghost');
label(p,'알림 종류',16,160,{size:12,style:'Bold',color:'#333333'});
[['후보 카드 (1차 · 2차)',true],['배치 요약',true],['예산 경고 · 초과',true],['배치 미실행 경고',true],['소스 차단 · 로그인 만료',true],['카테고리 확인 대기 건수',false]].forEach((a,i)=>{const col=i%2,row=Math.floor(i/2);toggle(p,16+col*280,186+row*34,a[1]);label(p,a[0],62+col*280,188+row*34,{size:12,color:'#333333'});});
label(p,'관리자 계정',16,300,{size:12,style:'Bold',color:'#333333'});
input(p,16,322,170,'현재 비밀번호','••••••••');input(p,206,322,170,'새 비밀번호','••••••••');btn(p,396,342,'변경','ghost',100);
const sv2=box(f,{x:220,y:944,w:1220,h:56,fill:'#FFFFFF',stroke:'#E0E0E0',r:0,name:'저장 바'});label(sv2,'키와 토큰은 암호화해 settings에 저장 · .env 값은 화면 값이 없을 때만 사용',24,19,{size:12,color:'#666666'});btn(sv2,1084,10,'저장','primary',112);
return {removed,sectionId:S.id,createdScreenIds:created};
