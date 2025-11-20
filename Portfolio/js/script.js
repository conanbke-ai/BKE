/* ====================================================================
    0. 포트폴리오 데이터 정의 (JSON Data)
    ==================================================================== */
const portfolioData = {
  personal: {
    name: "배경은", // 💡 포트폴리오 소유자 이름으로 변경해주세요
    typingTexts: [
      "개발자 배경은입니다.",
      "Back-end Developer",
      "AIoT Data Engineer",
    ],
  },
  about: {
    summary: `
            AI와 IoT를 연계하여 데이터를 분석하고 의미 있는 인사이트로 전환하는 개발자입니다.
            실무 프로젝트 경험을 바탕으로 문제 해결 능력을 발휘하며, 새로운 기술을 빠르게 습득합니다.
            팀과의 원활한 협업을 통해 효율적이고 실용적인 솔루션을 제공합니다.
            사용자 중심의 접근으로, 기술이 실제 가치를 만들어내도록 집중합니다.
            항상 배우고 성장하며, 도전적인 프로젝트에서 성과를 창출하는 것을 즐깁니다.
        `,
    // **About Me 왼쪽 구조 개편을 위해 데이터 구조 변경**
    detailedIntro: [
      {
        badge: "클린 코드 & 테스트",
        icon: "fas fa-clipboard-check",
        content:
          "Jest, React Testing Library를 활용하여 TDD 기반의 개발을 지향합니다. 가독성과 재사용성을 최우선으로 합니다.",
      },
      {
        badge: "상태 관리 전문가",
        icon: "fas fa-sync-alt",
        content:
          "Redux, Recoil 등 다양한 상태 관리 라이브러리 경험을 바탕으로 프로젝트 규모에 맞는 최적의 솔루션을 적용합니다.",
      },
      {
        badge: "협업 & 설계 능력",
        icon: "fas fa-handshake",
        content:
          "Figma 기반의 디자인 시스템을 코드로 구현하고, 백엔드 개발자들과 RESTful API 명세를 명확히 정의하여 효율적인 협업을 이끌어냅니다.",
      },
      {
        badge: "협업 & 설계 능력",
        icon: "fas fa-handshake",
        content:
          "Figma 기반의 디자인 시스템을 코드로 구현하고, 백엔드 개발자들과 RESTful API 명세를 명확히 정의하여 효율적인 협업을 이끌어냅니다.",
      },
    ],
    strengths: [
      {
        icon: "fas fa-rocket",
        title: "최적화 및 성능 개선",
        description:
          "Webpack, Vite 등의 빌드 도구를 활용하여 초기 로딩 속도 최적화 및 번들 사이즈 개선 경험이 풍부합니다.",
      },
      {
        icon: "fas fa-code-branch",
        title: "Git & 협업 문화",
        description:
          "Git Flow 전략 기반의 협업 환경에서 PR 리뷰 및 코드 컨벤션을 엄수하며 팀 생산성을 높입니다.",
      },
      {
        icon: "fas fa-lightbulb",
        title: "문제 해결 능력",
        description:
          "복잡한 요구사항을 기술적으로 분해하고, 예상치 못한 런타임 오류에 대해 논리적인 디버깅을 수행합니다.",
      },
      {
        icon: "fas fa-lightbulb",
        title: "문제 해결 능력",
        description:
          "복잡한 요구사항을 기술적으로 분해하고, 예상치 못한 런타임 오류에 대해 논리적인 디버깅을 수행합니다.",
      },
    ],
    certifications: [
      "정보처리기사 (2022.05)",
      "SQLD (2020.10)",
      "빅데이터분석기사 (2024.01)",
    ],
  },
  skills: [
    { name: "JavaScript", level: 90, icon: "fab fa-js" },
    { name: "React", level: 85, icon: "fab fa-react" },
    { name: "TypeScript", level: 75, icon: "fas fa-flask" },
    { name: "Node.js", level: 60, icon: "fab fa-node-js" },
    { name: "CSS/SASS", level: 95, icon: "fab fa-css3-alt" },
    { name: "HTML5", level: 95, icon: "fab fa-html5" },
    { name: "Git/Github", level: 90, icon: "fab fa-github" },
    { name: "AWS/Deploy", level: 50, icon: "fab fa-aws" },
  ],
  career: [
    {
      date: "2022.01 - 현재",
      title: "사업수행팀",
      company: "(주)메가투스",
      description: "연계 솔루션 기업 <br>- 행정안전부 주관 지방세입 프로젝트 참여",
    },
    {
      date: "2025.09 - 2026.02(5개월)",
      title: "신재생에너지기반 Iot 개발자과정",
      company: "CodingOn",
      description: "<br>- AI 기반 태양광 발전량 예측 및 이상치 탐지/분석,<br>",
    },
    {
      date: "2021.04 - 2021.11(6개월)",
      title: "JAVA 웹 개발자 양성과정",
      company: "KG IT Bank",
      description:
        "자바 스프링 기반 JAVA 웹 프로젝트 경험 <br>- 호텔 예약 홈페이지",
    },
    {
      date: "2018.04 - 2018.12(6개월)",
      title: "인턴",
      company: "한국식품안전관리인증원",
      description:
        "소규모 식품업체 대상 맞춤형 현장지도 <br>- 관련법령/위해예방관리계획 지도 및 모니터링 등",
    },
    {
      date: "2014.02 - 2018.08",
      title: "식품영양학과 바이오식품과학 전공",
      company: "우송대학교",
      description: "4년제 대학 졸 <br>- 미생물/분석 실험실 경험",
    },
  ],
  projects: [
    {
      id: 1,
      title: "실시간 협업 웹 에디터 (CodeSync)",
      subtitle: "React와 Socket.io를 활용한 실시간 코드 편집 플랫폼.",
      image: "projects/codesync_main.jpg",
      duration: "2024.03 - 2024.06 (4개월)",
      tags: [
        "React",
        "TypeScript",
        "Socket.io",
        "Monaco Editor",
        "Express",
        "MongoDB",
      ],
      description:
        "수십 명이 동시에 접속하여 코드를 편집할 수 있는 실시간 웹 에디터 개발. 충돌 없는 문서 동기화를 위해 Operational Transformation(OT) 알고리즘을 구현하고 성능을 최적화했습니다.",
      features: [
        "다중 사용자 실시간 동시 편집 및 커서 동기화",
        "편집 기록 관리 및 롤백 기능 구현",
        "다양한 프로그래밍 언어 문법 강조",
        "접근 권한 설정 및 방 관리 기능",
      ],
      images: [
        "projects/codesync_detail_1.jpg",
        "projects/codesync_detail_2.jpg",
        "projects/codesync_detail_3.jpg",
      ],
      github: "https://github.com/YourUsername/CodeSync",
      demo: "https://demo.codesync.com",
    },
    {
      id: 2,
      title: "AI 기반 영양 관리 서비스 (NutriMate)",
      subtitle: "사용자 식단 분석 및 맞춤형 영양 피드백 제공 서비스.",
      image: "projects/nutrimate_main.jpg",
      duration: "2023.10 - 2024.01 (3개월)",
      tags: ["Next.js", "Recoil", "Tailwind CSS", "Python API", "PostgreSQL"],
      description:
        "프론트엔드는 Next.js 기반으로 SSR/SSG를 도입하여 SEO 및 성능을 극대화했습니다. 사용자 친화적인 UI/UX를 설계하고, 백엔드 AI 분석 결과를 시각화했습니다.",
      features: [
        "사용자 식단 사진 업로드 및 AI 분석 결과 시각화",
        "일일, 주간, 월간 영양소 섭취량 추이 차트 제공",
        "개인 건강 목표에 따른 맞춤형 식단 추천",
        "반응형 웹 디자인 및 모바일 앱 연동",
      ],
      images: [
        "projects/nutrimate_detail_1.jpg",
        "projects/nutrimate_detail_2.jpg",
      ],
      github: "https://github.com/YourUsername/NutriMate",
      demo: "",
    },
    {
      id: 3,
      title: "맞춤형 여행 플래너 (Travel-Wiz)",
      subtitle: "사용자 선호도 기반의 동적 경로 추천 웹 앱.",
      image: "projects/travelwiz_main.jpg",
      duration: "2023.05 - 2023.08 (4개월)",
      tags: ["Vue.js", "Vuex", "SCSS", "Google Maps API", "Django"],
      description:
        "Vue.js 컴포넌트 기반으로 복잡한 지도 인터랙션 및 경로 추천 알고리즘 결과를 효율적으로 표시했습니다. TMap, Google Maps API와의 연동을 최적화하고 사용자 피드백을 반영하여 경로를 동적으로 변경하는 기능을 구현했습니다.",
      features: [
        "사용자 테마 선호도 기반 여행지 추천",
        "드래그 앤 드롭을 통한 경로 순서 변경",
        "실시간 예상 소요 시간 및 이동 수단 정보 제공",
        "여행 일정 PDF 출력 기능",
      ],
      images: [
        "projects/travelwiz_detail_1.jpg",
        "projects/travelwiz_detail_2.jpg",
        "projects/travelwiz_detail_3.jpg",
      ],
      github: "https://github.com/YourUsername/Travel-Wiz",
      demo: "https://demo.travelwiz.com",
    },
    {
      id: 4,
      title: "E-Commerce 백오피스 시스템",
      subtitle: "대규모 상품 및 주문 관리를 위한 관리자 페이지.",
      image: "projects/ecommerce_main.jpg",
      duration: "2022.11 - 2023.02 (4개월)",
      tags: ["React", "Redux Toolkit", "Material UI", "Spring Boot", "MySQL"],
      description:
        "대량의 데이터를 빠르게 처리하고 시각화하기 위해 React와 Redux Toolkit을 사용한 SPA(Single Page Application)로 구현했습니다. 복잡한 검색 필터링 및 데이터 테이블 최적화에 집중했습니다.",
      features: [
        "실시간 주문/재고 현황 대시보드",
        "대용량 데이터 테이블 가상화(Virtualization)",
        "직관적인 상품 등록 및 수정 폼",
        "사용자 권한별 접근 제어 (RBAC)",
      ],
      images: [
        "projects/ecommerce_detail_1.jpg",
        "projects/ecommerce_detail_2.jpg",
      ],
      github: "https://github.com/YourUsername/Ecommerce-Admin",
      demo: "",
    },
  ],
};

let currentSlideIndex = 1;
const body = document.body;

/* ====================================================================
    1. 초기화 및 데이터 로딩
    ==================================================================== */

document.addEventListener("DOMContentLoaded", () => {
  // 1. 데이터 로드 및 렌더링
  renderAllSections();

  // 2. 이벤트 리스너 설정
  setupThemeToggle();
  setupModalEvents();
  setupScrollEvents();
  setupCursorEvents();
  setupMagneticButtons();
  setupSkillsObserver(); // 스킬 애니메이션을 위한 Observer 설정

  // 3. 애니메이션 시작
  startTypingAnimation(portfolioData.personal.typingTexts);
});

function renderAllSections() {
  renderAboutSection();
  renderSkillsSection();
  renderCareerSection();
  renderProjectsSection();
}

/* ====================================================================
    2. 데이터 렌더링 함수
    ==================================================================== */

// 💡 About Me 섹션 렌더링 (개편된 디자인 반영)
function renderAboutSection() {
  const summaryEl = document.getElementById("about-me-summary");
  const detailsEl = document.getElementById("about-me-details");

  // About-Left: Summary & Detailed Intro (새로운 배지 카드 구조)
  const detailedCards = portfolioData.about.detailedIntro
    .map(
      (item) => `
            <div class="badge-card glass-card">
                <div class="key-badge">
                    <i class="${item.icon}"></i> ${item.badge}
                </div>
                <p>${item.content}</p>
            </div>
        `
    )
    .join("");

  summaryEl.innerHTML = `
        <p class="profile-intro">${portfolioData.about.summary}</p>
        <div class="badge-card-grid">${detailedCards}</div>
    `;

  // About-Right: Strengths & Certifications (자격증 아이콘 변경)
  let strengthsHtml = '<div class="strength-grid">';
  portfolioData.about.strengths.forEach((s) => {
    strengthsHtml += `
            <div class="strength-block">
                <h4><i class="${s.icon}"></i> ${s.title}</h4>
                <p>${s.description}</p>
            </div>
        `;
  });
  strengthsHtml += "</div>";

  // 자격증 아이콘을 fas fa-graduation-cap으로 변경
  const certIcon = "fas fa-graduation-cap";
  const certIconDetail = "fas fa-check";
  let certsHtml = `
        <div class="cert-list">
            <h4><i class="${certIcon}"></i> 자격증</h4>
            <ul>
                ${portfolioData.about.certifications
                  .map((c) => `<li><i class="${certIconDetail}"></i> ${c}</li>`)
                  .join("")}
            </ul>
        </div>
    `;

  detailsEl.innerHTML = strengthsHtml + certsHtml;
}

// 💡 Skills 섹션 렌더링 (원형 프로그레스 바 구현 및 애니메이션 준비)
function renderSkillsSection() {
  const skillsListEl = document.getElementById("skills-list");
  skillsListEl.innerHTML = portfolioData.skills
    .map((skill) => {
      const radius = 55;
      const circumference = 2 * Math.PI * radius;
      const offset = circumference; // 초기에는 100% (offset 0)로 설정합니다.

      return `
            <div class="skill-item reveal" data-level="${skill.level}">
                <div class="circular-progress-container">
                    <svg class="circular-progress-svg" width="130" height="130" viewBox="0 0 130 130">
                        <circle class="circular-progress-track" cx="65" cy="65" r="${radius}" />
                        <circle 
                            class="circular-progress-bar" 
                            cx="65" 
                            cy="65" 
                            r="${radius}" 
                            data-circumference="${circumference}"
                            style="stroke-dasharray: ${circumference}; stroke-dashoffset: ${offset};"
                        />
                    </svg>
                    <span class="skill-level-text code-font">0%</span>
                </div>
                <div class="skill-name-wrapper">
                    <i class="${skill.icon} skill-icon"></i>
                    <span class="skill-name">${skill.name}</span>
                </div>
            </div>
        `;
    })
    .join("");
}

// 💡 스킬 원형 바 애니메이션 로직 (복구 및 수정)
function setupSkillsObserver() {
  const skillItems = document.querySelectorAll(".skill-item");

  // 애니메이션이 이미 실행되었는지 추적
  const animatedSkills = new Set();

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        const skillItem = entry.target;
        const skillLevel = parseInt(skillItem.dataset.level);
        const progressBar = skillItem.querySelector(".circular-progress-bar");
        const levelText = skillItem.querySelector(".skill-level-text");

        // Intersection Observer가 지원되지 않는 경우 예외 처리
        if (!progressBar || !levelText) return;

        const circumference = parseFloat(progressBar.dataset.circumference);

        if (entry.isIntersecting && !animatedSkills.has(skillItem)) {
          // 1. 애니메이션 실행 (offset 변경)
          const targetOffset =
            circumference - (skillLevel / 100) * circumference;

          // CSS 트랜지션을 위해 잠시 시간을 준 후 offset 변경
          setTimeout(() => {
            progressBar.style.transition = "stroke-dashoffset 1.5s ease-out";
            progressBar.style.strokeDashoffset = targetOffset;
          }, 50);

          // 2. 숫자 카운트 애니메이션
          let currentLevel = 0;
          const duration = 1500; // 1.5초
          const stepTime = 10;
          const steps = duration / stepTime;
          const stepValue = skillLevel / steps;

          const timer = setInterval(() => {
            currentLevel += stepValue;
            if (currentLevel >= skillLevel) {
              currentLevel = skillLevel;
              clearInterval(timer);
            }
            levelText.textContent = `${Math.floor(currentLevel)}%`;
          }, stepTime);

          animatedSkills.add(skillItem); // 애니메이션 실행 완료 표시
        }
        // 섹션에서 벗어나거나, 이미 실행된 스킬은 다시 애니메이션하지 않음 (반복 방지)
      });
    },
    { threshold: 0.7, once: false }
  ); // 70% 보일 때 실행

  skillItems.forEach((item) => observer.observe(item));
}

// Career 섹션 렌더링 (날짜 크기 및 강조 수정)
function renderCareerSection() {
  const timelineEl = document.getElementById("timeline");
  timelineEl.innerHTML = portfolioData.career
    .map((item, index) => {
      // 첫 번째 항목에만 강조 클래스를 추가합니다. (CSS에서 처리)
      const highlightClass = index === 0 ? "highlight-item" : "";

      return `
            <div class="timeline-item reveal ${highlightClass}">
                <div class="timeline-date code-font">${item.date}</div>
                <div class="timeline-dot"></div> 
                <div class="timeline-content glass-card">
                    <h4>${item.title} <br>
                      <span class="company-name">@ ${item.company}</span>
                    </h4>
                    <p class="description">${item.description}</p>
                </div>
            </div>
        `;
    })
    .join("");
}

// Projects 섹션 렌더링 (4개, 2x2 정렬)
function renderProjectsSection() {
  const projectsGridEl = document.getElementById("projects-grid");
  projectsGridEl.innerHTML = portfolioData.projects
    .map((project) => {
      const tagsHtml = project.tags
        .map((tag) => `<span>${tag}</span>`)
        .join("");
      return `
            <div class="project-card glass-card reveal" data-project-id="${project.id}" onclick="openProjectModal(${project.id})">
                <img src="${project.image}" alt="${project.title} Thumbnail" class="project-image">
                <div class="project-info">
                    <div>
                        <h3>${project.title}</h3>
                        <p>${project.subtitle}</p>
                    </div>
                    <div class="tags">${tagsHtml}</div>
                </div>
            </div>
        `;
    })
    .join("");
}

/* ====================================================================
    3. Dark Mode Toggle (생략 - 기능 변경 없음)
    ==================================================================== */

function setupThemeToggle() {
  const toggle = document.getElementById("theme-toggle");
  const body = document.body;
  const currentTheme = localStorage.getItem("theme") || "light";

  if (currentTheme === "dark") {
    body.setAttribute("data-theme", "dark");
    toggle.checked = true;
  } else {
    body.setAttribute("data-theme", "light");
    toggle.checked = false;
  }

  setTimeout(() => {
    body.classList.remove("touch");
  }, 500);

  toggle.addEventListener("change", () => {
    if (toggle.checked) {
      body.setAttribute("data-theme", "dark");
      localStorage.setItem("theme", "dark");
    } else {
      body.setAttribute("data-theme", "light");
      localStorage.setItem("theme", "light");
    }
  });
}

/* ====================================================================
    4. Hero Typing Animation (생략 - 기능 변경 없음)
    ==================================================================== */

async function startTypingAnimation(texts) {
  const typingTextEl = document.getElementById("typing-text");
  let textIndex = 0;

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  const type = async (text) => {
    for (const char of text) {
      typingTextEl.textContent += char;
      await sleep(80);
    }
  };

  const erase = async () => {
    while (typingTextEl.textContent.length > 0) {
      typingTextEl.textContent = typingTextEl.textContent.slice(0, -1);
      await sleep(40);
    }
  };

  const loop = async () => {
    while (true) {
      const currentText = texts[textIndex];
      await type(currentText);
      await sleep(2000);
      await erase();
      textIndex = (textIndex + 1) % texts.length;
      await sleep(500);
    }
  };

  loop();
}

/* ====================================================================
    5. Scroll Events (Progress Bar & Reveal) (생략 - 기능 변경 없음)
    ==================================================================== */

function setupScrollEvents() {
  const scrollProgress = document.querySelector(".scroll-progress");
  const sections = document.querySelectorAll(".reveal");
  const navItems = document.querySelectorAll(".floating-nav .nav-item");
  const floatingNav = document.querySelector(".floating-nav");

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("active");
        }
      });
    },
    { threshold: 0.1 }
  );

  sections.forEach((section) => observer.observe(section));

  window.addEventListener("scroll", () => {
    const scrollTop = document.documentElement.scrollTop;
    const scrollHeight =
      document.documentElement.scrollHeight -
      document.documentElement.clientHeight;
    const progress = (scrollTop / scrollHeight) * 100;
    scrollProgress.style.width = `${progress}%`;

    let currentActive = "hero";
    document.querySelectorAll(".section").forEach((section) => {
      const top = section.offsetTop;
      if (scrollTop >= top - 300) {
        currentActive = section.id;
      }
    });

    navItems.forEach((item) => {
      item.classList.remove("active");
      if (item.getAttribute("href").includes(currentActive)) {
        item.classList.add("active");
      }
    });

    if (scrollTop > window.innerHeight - 100) {
      floatingNav.style.opacity = "1";
      floatingNav.style.visibility = "visible";
    } else {
      floatingNav.style.opacity = "0";
      floatingNav.style.visibility = "hidden";
    }
  });

  window.dispatchEvent(new Event("scroll"));
}

/* ====================================================================
    6. Modal & Slider Logic (모달 개선)
    ==================================================================== */

const modal = document.getElementById("projectModal");
const closeButton = document.querySelector(".close-button");

function setupModalEvents() {
  closeButton.addEventListener("click", closeModal);
  window.addEventListener("click", (event) => {
    if (event.target === modal) {
      closeModal();
    }
  });
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && modal.classList.contains("open")) {
      closeModal();
    }
    // 슬라이더 키보드 네비게이션
    if (modal.classList.contains("open")) {
      if (event.key === "ArrowRight") plusSlides(1);
      if (event.key === "ArrowLeft") plusSlides(-1);
    }
  });
}

window.openProjectModal = function (projectId) {
  const project = portfolioData.projects.find((p) => p.id === projectId);
  if (!project) return;

  // 1. 모달 데이터 채우기 (이전과 동일)
  document.getElementById("modal-title").textContent = project.title;
  document.getElementById("modal-subtitle").textContent = project.subtitle;
  document.getElementById("modal-description").textContent =
    project.description;
  document.getElementById("modal-duration").textContent = project.duration;

  // Tags
  const tagsContainer = document.getElementById("modal-tags");
  tagsContainer.innerHTML = project.tags
    .map((tag) => `<span class="tag-in-modal">${tag}</span>`)
    .join("");

  // Features
  const featuresList = document.getElementById("modal-features");
  featuresList.innerHTML = project.features
    .map((f) => `<li><i class="fas fa-check-circle"></i> ${f}</li>`)
    .join("");

  // Links
  const githubLink = document.getElementById("modal-github");
  const demoLink = document.getElementById("modal-demo");

  githubLink.href = project.github || "#";
  githubLink.style.display = project.github ? "flex" : "none";

  demoLink.href = project.demo || "#";
  demoLink.style.display = project.demo ? "flex" : "none";

  // 2. 이미지 슬라이더 생성 (하단 인디케이터 추가)
  const slidesContainer = document.getElementById("modal-slides");
  let slidesHtml = project.images
    .map(
      (imgSrc) =>
        `<div class="project-slide-item"><img src="${imgSrc}" alt="${project.title} Screenshot"></div>`
    )
    .join("");

  const dotsContainer = `<div class="slide-dots-container">
        ${project.images
          .map(
            (_, index) =>
              `<span class="slide-dot" onclick="currentSlide(${
                index + 1
              })"></span>`
          )
          .join("")}
    </div>`;

  slidesContainer.innerHTML = slidesHtml;
  // 슬라이더 밑에 인디케이터를 추가하기 위해 DOM을 직접 조작해야 함 (HTML 구조상 별도 엘리먼트에 추가)
  const sliderContainer = document.querySelector(".project-slider");
  // 기존 dots container 제거 (중복 방지)
  const existingDots = sliderContainer.querySelector(".slide-dots-container");
  if (existingDots) existingDots.remove();

  sliderContainer.insertAdjacentHTML("beforeend", dotsContainer);

  // 3. 모달 열기 및 슬라이드 초기화
  modal.classList.add("open");
  body.classList.add("modal-open");
  currentSlideIndex = 1;
  showSlides(currentSlideIndex);
};

function closeModal() {
  modal.classList.remove("open");
  body.classList.remove("modal-open");
}

// 이미지 슬라이더 핵심 로직
window.plusSlides = function (n) {
  showSlides((currentSlideIndex += n));
};

window.currentSlide = function (n) {
  showSlides((currentSlideIndex = n));
};

function showSlides(n) {
  const slides = document.getElementsByClassName("project-slide-item");
  const dots = document.getElementsByClassName("slide-dot");

  if (slides.length === 0) return;

  if (n > slides.length) {
    currentSlideIndex = 1;
  }
  if (n < 1) {
    currentSlideIndex = slides.length;
  }

  for (let i = 0; i < slides.length; i++) {
    slides[i].style.display = "none";
  }
  for (let i = 0; i < dots.length; i++) {
    dots[i].className = dots[i].className.replace(" active", "");
  }

  slides[currentSlideIndex - 1].style.display = "block";
  dots[currentSlideIndex - 1].className += " active";
}

/* ====================================================================
    7. Custom Cursor & Magnetic Button (생략 - 기능 변경 없음)
    ==================================================================== */

function setupCursorEvents() {
  const cursorDot = document.querySelector(".cursor-dot");
  const cursorOutline = document.querySelector(".cursor-dot-outline");

  window.addEventListener("mousemove", (e) => {
    const posX = e.clientX;
    const posY = e.clientY;

    cursorDot.style.left = `${posX}px`;
    cursorDot.style.top = `${posY}px`;

    cursorOutline.style.left = `${posX}px`;
    cursorOutline.style.top = `${posY}px`;

    cursorOutline.animate(
      {
        left: `${posX}px`,
        top: `${posY}px`,
      },
      { duration: 500, fill: "forwards" }
    );
  });

  document
    .querySelectorAll(
      "a, button, .magnetic-btn, .project-card, .theme-toggle-label, .close-button, .slide-dot"
    )
    .forEach((el) => {
      el.addEventListener("mouseenter", () => body.classList.add("hovering"));
      el.addEventListener("mouseleave", () =>
        body.classList.remove("hovering")
      );
    });
}

function setupMagneticButtons() {
  const magneticBtns = document.querySelectorAll(".magnetic-btn");

  magneticBtns.forEach((btn) => {
    btn.addEventListener("mousemove", (e) => {
      const rect = btn.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;

      const centerX = rect.width / 2;
      const centerY = rect.height / 2;

      const deltaX = (x - centerX) * 0.2;
      const deltaY = (y - centerY) * 0.2;

      btn.style.transform = `translate(${deltaX}px, ${deltaY}px)`;
    });

    btn.addEventListener("mouseleave", () => {
      btn.style.transform = `translate(0, 0)`;
    });
  });
}
