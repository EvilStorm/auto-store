// 01 프로세스 · 02 상태 머신 · 03 구성도 문구를 v2(멀티 소스)로 갱신. use_figma(code) 또는 Scripter로 실행.
const FAM='Noto Sans KR';
const F=s=>({family:FAM,style:s});
await Promise.all(['Regular','Medium','Bold'].map(s=>figma.loadFontAsync(F(s))));
const page=await figma.getNodeByIdAsync('112:2');
await figma.setCurrentPageAsync(page);
const hex=h=>{const n=parseInt(h.slice(1),16);return{r:((n>>16)&255)/255,g:((n>>8)&255)/255,b:(n&255)/255}};
const solid=(h,o)=>{const p={type:'SOLID',color:hex(h)};if(o!==undefined)p.opacity=o;return p};
function text(str,o={}){const {size=14,style='Regular',color='#1F1F1F',w,align='LEFT',lh}=o;const t=figma.createText();t.fontName=F(style);t.characters=str;t.fontSize=size;t.fills=[solid(color)];if(lh)t.lineHeight={unit:'PIXELS',value:lh};t.textAlignHorizontal=align;if(w){t.resize(w,10);t.textAutoResize='HEIGHT';}return t;}
function label(parent,str,x,y,o={}){const t=text(str,o);t.x=x;t.y=y;parent.appendChild(t);return t;}
function box(parent,o){const {x,y,w,h,fill='#FFFFFF',stroke='#D9D9D9',sw=1,r=8,name='box'}=o;const f=figma.createFrame();f.name=name;f.resize(w,h);f.x=x;f.y=y;f.fills=fill?[solid(fill)]:[];f.strokes=stroke?[solid(stroke)]:[];f.strokeWeight=sw;f.cornerRadius=r;f.clipsContent=false;parent.appendChild(f);return f;}
const changed=[];
function retext(sec,map){for(const t of sec.findAllWithCriteria({types:['TEXT']})){const nv=map[t.characters];if(nv!==undefined){t.characters=nv;changed.push(t.id);}}}
// 01
const s1=await figma.getNodeByIdAsync('526:2');
retext(s1,{'① 수집기':'① 소스별 수집','1688 목록 수집\n가격·최소수량·무게·재질':'등록 소스 × 카테고리\n어댑터가 원시 데이터 반환','② 필터':'② 정규화 · 필터','제외 규칙 적용\n목록통관 배제 품목':'통화·언어·카테고리 별칭\n브랜드 로고 감지 · 제외 규칙','1688.com':'도매 사이트들','Playwright 로그인 세션':'1688 · 타오바오 · NETSEA …\n소스별 로그인 프로필','Claude':'AI (선택: Claude / Gemini / OpenAI)','재질·품목 정규화':'언어 무관 정규화 · 로고 감지\n카테고리 제안 → 확인 큐','Claude + 이미지 생성':'AI 텍스트 + 이미지 생성 (선택 제공자)','OCR·인페인팅·재구성':'OCR·인페인팅·템플릿 렌더링\n예산 잔여 확인 후 실행','02:00':'배치','배치 시작':'시각 설정 가능','후보 카드 전송\n매일 08:00':'마진율순 상위 N건 (기본 10)\n알림 시각 설정 가능','⑦ 콘텐츠 생성':'⑦ 콘텐츠 생성','엑셀 행 추가\n이미지 폴더':'이미지 → Supabase 업로드\n엑셀 행 (이미지 공개 URL)','output/날짜/':'Supabase Storage + output/','엑셀 + 이미지 폴더':'공개 이미지 URL + 엑셀 · 로컬 사본','상품 상세 페이지':'해당 소스 어댑터의 상세 수집','수출입은행 (실패 시 고정값)':'자동 수집만: 수출입은행 API\n→ 네이버 금융 크롤링 → 마지막값','하루 1회 새벽 배치 → 아침 텔레그램 후보 수신 → 2단계 승인 → 등록 패키지(엑셀) 산출':'v2 멀티 소스 · 하루 1회 새벽 배치 → 아침 텔레그램 후보 수신 → 2단계 승인 → 등록 패키지(엑셀) 산출','카테고리·제외 규칙·비용 설정':'소스·카테고리 매핑·제외 규칙·비용'});
for(const t of s1.findAllWithCriteria({types:['TEXT']})){if(t.characters.startsWith('거절 → 종료')){t.characters='거절 → 종료 · 보류 → 다음날 다시 알림 · 수정 요청 → ⑦ 재실행 · 캡차 차단 → 그 소스만 당일 중단, 아침 요약에 집계 · 표준 카테고리 미확정 → mapping_pending, 확인 후 재개 · 단계 실패 → error, 관리자 재시도';changed.push(t.id);}}
// 01 하단: ⑩ 감시 안내 띠
const mo=box(s1,{x:120,y:1150,w:2480,h:70,fill:'#FFF7E0',stroke:'#B7791F',r:10,name:'⑩ 등록 상품 감시'});
label(mo,'⑩ 등록 상품 감시 (별도 주기 · 관리자 설정, 기본 3일)',16,10,{size:14,style:'Bold',color:'#8A6D00'});
label(mo,'관리자가 "등록 완료"를 표시한 상품(listed)의 소스를 재점검 → 가격 ±임계값 · 품절 · 옵션 품절 · 최소수량 변경 · 페이지 삭제 감지 → 원가 재계산 → 텔레그램 [판매가 수정] [판매 중지] [무시]. 상세는 보드 08.',16,36,{size:12,color:'#5A4A00',w:2440});
// 02
const s2=await figma.getNodeByIdAsync('526:191');
const nb=box(s2,{x:120,y:760,w:1000,h:90,fill:'#FFF7E0',stroke:'#B7791F',r:10,name:'v2 추가 상태'});
label(nb,'v2 추가 상태',20,12,{size:14,style:'Bold',color:'#8A6D00'});
label(nb,'collected 뒤에 normalized(② 정규화 완료)가 들어가고, 표준 카테고리를 모르는 상품은 mapping_pending에서 멈춘다. 카테고리 매핑 화면의 확인 큐에서 승인되면 matched 단계로 이어진다. 품목 유형을 모르면 목록통관 배제 여부를 판단할 수 없기 때문에 매칭으로 넘기지 않는다.',20,36,{size:12,color:'#5A4A00',w:960,lh:18});
// 02 등록 후 상태 체인 (packaged → listed → 변동 → 결정)
function pill(x,y,w,t,s,fill,stroke){const f=figma.createFrame();f.name=t;f.resize(w,64);f.x=x;f.y=y;f.fills=[solid(fill)];f.strokes=[solid(stroke)];f.strokeWeight=1;f.cornerRadius=32;f.clipsContent=false;s2.appendChild(f);const a=label(f,t,0,12,{size:14,style:'Bold',w:w,align:'CENTER'});const b=label(f,s,0,36,{size:11,color:'#666666',w:w,align:'CENTER'});return f;}
function arr(x1,y1,x2,y2,head=true){const pad=8;const minx=Math.min(x1,x2)-pad,miny=Math.min(y1,y2)-pad,w=Math.abs(x2-x1)+pad*2,h=Math.abs(y2-y1)+pad*2;const ax=x1-minx,ay=y1-miny,bx=x2-minx,by=y2-miny;let hd='';if(head){if(x2>x1)hd=`M${bx} ${by} L${bx-8} ${by-4.5} L${bx-8} ${by+4.5} Z`;else if(y2>y1)hd=`M${bx} ${by} L${bx-4.5} ${by-8} L${bx+4.5} ${by-8} Z`;else if(y2<y1)hd=`M${bx} ${by} L${bx-4.5} ${by+8} L${bx+4.5} ${by+8} Z`;else hd=`M${bx} ${by} L${bx+8} ${by-4.5} L${bx+8} ${by+4.5} Z`;}const n=figma.createNodeFromSvg(`<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg"><path d="M${ax} ${ay} L${bx} ${by}" stroke="#8A8A8A" stroke-width="2" fill="none"/>${hd?`<path d="${hd}" fill="#8A8A8A"/>`:''}</svg>`);n.name=head?'arrow':'line';n.x=minx;n.y=miny;s2.appendChild(n);}
label(s2,'등록 후 (⑩ 감시)',1240,730,{size:13,style:'Bold',color:'#555555'});
pill(1240,760,180,'listed','관리자 "등록 완료" 표시','#D9F2E3','#2F855A');
arr(1420,792,1489,792);
pill(1490,760,200,'변동 감지','가격 · 품절 · 옵션 · MOQ · 삭제','#FFE4C4','#C05621');
arr(1690,792,1759,792);
pill(1760,760,180,'[판매가 수정]','→ listed (판매가 갱신)','#FFFFFF','#4A5568');
pill(1960,760,180,'[판매 중지]','→ suspended','#EDEDED','#9A9A9A');
pill(2160,760,180,'[무시]','→ listed (확인 처리)','#FFFFFF','#4A5568');
// 판매 중지 · 무시로 가는 선은 카드 아래쪽 버스(y=850)로 우회
arr(1590,824,1590,850,false);arr(1590,850,2250,850,false);arr(2050,850,2050,825);arr(2250,850,2250,825);
label(s2,'suspended 상품은 복구(재판매) 감지 시 다시 알림 → listed',1960,866,{size:11,color:'#666666'});
// 03
const s3=await figma.getNodeByIdAsync('526:303');
retext(s3,{'pipeline/ ① ② ③ ④ · ⑥ ⑦ · ⑨':'① 소스별 수집 → ② 정규화 → ③④ · ⑥⑦ · ⑨','Chromium · 로그인 프로필 유지':'소스별 Chromium 프로필 (로그인 유지)','APScheduler\n02:00 배치 · 08:00 알림':'APScheduler\n수집·알림 시각은 관리자 설정','Claude API':'AI API (Claude / Gemini / OpenAI 선택)','이미지 생성 API':'이미지 생성 API (Gemini / OpenAI 선택)','모드 C 전용 · 모델은 구현 시 선택':'모드 C 연출컷 전용 · 예산 상한 적용','llm_claude':'llm/ (3사)','.env (키·관리자 계정)\nselectors.yaml (1688 DOM)':'.env (AI 키 · Supabase · 예산 · 스케줄)\nselectors/<key>.yaml · 화면 저장값 우선','products · matches · cost_estimates\napprovals · settings · run_logs':'sources · source_categories · canonical_categories\ncategory_aliases · products · matches · approvals','어댑터 계층 (adapters/)':'공통 어댑터 (adapters/)','목록·상세 크롤링 (로그인 계정)':'1688 · 타오바오 · 알리 · NETSEA · 슈퍼딜리버리 · 사용자 등록','집 PC 한 대 · 단일 사용자 · 외부 서비스는 어댑터 계층 뒤에 두어 교체 가능':'v2: 소스 어댑터 계층이 사이트 차이를 흡수하고, 공통 어댑터가 외부 서비스를 감싼다','검색어·매칭 판정·정규화·한국어화':'검색어 · 매칭 판정 · 다국어 정규화 · 카테고리 제안 · LLM 추출 어댑터','한국수출입은행':'수출입은행 API → 네이버 금융 크롤링 (자동, 수동 입력 없음)','exchange_rate':'exchange_rate (다통화)'});
for(const t of s3.findAllWithCriteria({types:['TEXT']})){if(t.characters==='1688.com'){t.characters='도매 사이트들 (소스 등록)';changed.push(t.id);}}
const sb=box(s3,{x:1300,y:960,w:380,h:80,fill:'#FFFFFF',stroke:'#2F855A',r:10,name:'Supabase Storage'});
label(sb,'Supabase Storage (공개 버킷)',0,18,{size:15,style:'Bold',w:380,align:'CENTER'});label(sb,'생성 이미지 공개 URL → 엑셀 일괄등록 · .env 접속 정보',0,44,{size:12,color:'#666666',w:380,align:'CENTER'});
const sbArrow=(pts)=>{for(let i=0;i<pts.length-1;i++){const last=i===pts.length-2;const [x1,y1]=pts[i],[x2,y2]=pts[i+1];const pad=8;const minx=Math.min(x1,x2)-pad,miny=Math.min(y1,y2)-pad,w=Math.abs(x2-x1)+pad*2,h=Math.abs(y2-y1)+pad*2;const ax=x1-minx,ay=y1-miny,bx=x2-minx,by=y2-miny;const hd=last?`<path d="M${bx} ${by} L${bx-8} ${by-4.5} L${bx-8} ${by+4.5} Z" fill="#8A8A8A"/>`:'';const n=figma.createNodeFromSvg(`<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg"><path d="M${ax} ${ay} L${bx} ${by}" stroke="#8A8A8A" stroke-width="2" fill="none" stroke-dasharray="6 5"/>${hd}</svg>`);n.name=last?'arrow':'line';n.x=minx;n.y=miny;s3.appendChild(n);}};
sbArrow([[1040,880],[1170,880],[1170,1000],[1299,1000]]);
const st=box(s3,{x:80,y:940,w:960,h:110,fill:'#FFE4C4',stroke:'#C05621',r:10,name:'소스 어댑터 계층'});
label(st,'소스 어댑터 계층 (sources/) · SourceAdapter 계약: open_session · list · detail · is_blocked',16,12,{size:14,style:'Bold',color:'#333333'});
['1688','taobao','aliexpress','netsea','superdelivery','generic_css','llm_extract'].forEach((a,i)=>{const p=box(st,{x:16+i*132,y:44,w:124,h:50,fill:'#FFFFFF',stroke:i>=5?'#C05621':'#A0A0A0',r:8,name:a});const t=label(p,a,0,0,{size:12,style:'Medium',color:'#333333',w:124,align:'CENTER',lh:16});t.y=(50-t.height)/2;});
return {changed:changed.length,added:[nb.id,st.id,sb.id,mo.id]};
