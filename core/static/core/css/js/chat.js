// chat.js
document.addEventListener('DOMContentLoaded', function() {
  // Элементы DOM
  const chatForm = document.getElementById('chat-form');
  const questionInput = document.getElementById('question-input');
  const chatMessages = document.getElementById('chat-messages');
  const submitBtn = document.getElementById('submit-btn');
  const loadingIndicator = document.getElementById('loading-indicator');
  
  // Фокус на поле ввода при загрузке
  if (questionInput) {
    questionInput.focus();
    questionInput.setSelectionRange(questionInput.value.length, questionInput.value.length);
  }
  
  // Автоскролл к последнему сообщению
  function scrollToBottom() {
    if (chatMessages) {
      chatMessages.scrollTop = chatMessages.scrollHeight;
    }
  }
  
  // Автоматическое увеличение высоты textarea
  function autoResizeTextarea() {
    if (questionInput) {
      questionInput.style.height = 'auto';
      questionInput.style.height = (questionInput.scrollHeight) + 'px';
      
      // Ограничение максимальной высоты
      const maxHeight = 200;
      if (questionInput.scrollHeight > maxHeight) {
        questionInput.style.height = maxHeight + 'px';
        questionInput.style.overflowY = 'auto';
      } else {
        questionInput.style.overflowY = 'hidden';
      }
    }
  }
  
  // Инициализация авторасширения textarea
  if (questionInput) {
    questionInput.addEventListener('input', autoResizeTextarea);
    autoResizeTextarea(); // Первоначальная настройка
  }
  
  // Показать индикатор загрузки
  function showLoading() {
    if (loadingIndicator) {
      loadingIndicator.style.display = 'block';
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="loading-dots"></span> Обработка';
      }
    }
    scrollToBottom();
  }
  
  // Скрыть индикатор загрузки
  function hideLoading() {
    if (loadingIndicator) {
      loadingIndicator.style.display = 'none';
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerHTML = `
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="22" y1="2" x2="11" y2="13"></line>
            <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
          </svg>
          Отправить
        `;
      }
    }
  }
  
  // Добавить сообщение в чат (для AJAX версии)
  function addMessage(message, isQuestion = false) {
    const messagesContainer = chatMessages;
    if (!messagesContainer) return;
    
    const now = new Date();
    const timeString = now.getHours().toString().padStart(2, '0') + ':' + 
                      now.getMinutes().toString().padStart(2, '0');
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${isQuestion ? 'question' : 'answer'}`;
    
    messageDiv.innerHTML = `
      <div class="message-header">
        <span class="message-sender">${isQuestion ? 'Вы' : 'Система'}</span>
        <span class="message-time">${timeString}</span>
      </div>
      <div class="bubble">
        ${message.replace(/\n/g, '<br>')}
      </div>
    `;
    
    messagesContainer.appendChild(messageDiv);
    scrollToBottom();
  }
  
  // Обработка отправки формы (AJAX версия - если решите реализовать)
  if (chatForm) {
    chatForm.addEventListener('submit', function(e) {
      const question = questionInput.value.trim();
      
      if (!question) {
        e.preventDefault();
        return;
      }
      
      // Показать индикатор загрузки
      showLoading();
      
      // Если вы хотите сделать AJAX отправку, раскомментируйте ниже
      /*
      e.preventDefault();
      
      // Создаем FormData
      const formData = new FormData(chatForm);
      
      // Отправляем AJAX запрос
      fetch(window.location.href, {
        method: 'POST',
        body: formData,
        headers: {
          'X-Requested-With': 'XMLHttpRequest'
        }
      })
      .then(response => response.json())
      .then(data => {
        if (data.success) {
          // Добавляем ответ в чат
          addMessage(question, true);
          addMessage(data.answer, false);
          
          // Очищаем поле ввода
          questionInput.value = '';
          autoResizeTextarea();
        } else {
          // Показываем ошибку
          alert(data.error || 'Произошла ошибка');
        }
        hideLoading();
      })
      .catch(error => {
        console.error('Error:', error);
        hideLoading();
        alert('Произошла ошибка при отправке запроса');
      });
      */
      
      // Для стандартной формы - просто показываем загрузку
      // Форма отправится обычным образом
    });
  }
  
  // Добавление индикаторов загрузки для кнопки
  const style = document.createElement('style');
  style.textContent = `
    .loading-dots {
      display: inline-block;
      position: relative;
      width: 20px;
      height: 20px;
    }
    
    .loading-dots:before,
    .loading-dots:after {
      content: '';
      position: absolute;
      top: 8px;
      width: 4px;
      height: 4px;
      border-radius: 50%;
      background: white;
      animation: loadingDots 1.5s infinite linear;
    }
    
    .loading-dots:before {
      left: 4px;
      animation-delay: 0s;
    }
    
    .loading-dots:after {
      left: 12px;
      animation-delay: 0.5s;
    }
    
    @keyframes loadingDots {
      0%, 60%, 100% {
        opacity: 0.3;
        transform: scale(0.8);
      }
      30% {
        opacity: 1;
        transform: scale(1);
      }
    }
  `;
  document.head.appendChild(style);
  
  // Первоначальный скролл к низу
  scrollToBottom();
  
  // Сохранение черновика в localStorage (опционально)
  if (questionInput) {
    const draftKey = 'chat_draft_' + window.location.pathname;
    
    // Восстановление черновика
    const savedDraft = localStorage.getItem(draftKey);
    if (savedDraft && !questionInput.value.trim()) {
      questionInput.value = savedDraft;
      autoResizeTextarea();
    }
    
    // Сохранение черновика при изменении
    let saveTimeout;
    questionInput.addEventListener('input', function() {
      clearTimeout(saveTimeout);
      saveTimeout = setTimeout(function() {
        localStorage.setItem(draftKey, questionInput.value);
      }, 500);
    });
    
    // Очистка черновика при отправке
    chatForm.addEventListener('submit', function() {
      localStorage.removeItem(draftKey);
    });
  }
  
  // Обработка клавиши Enter (Ctrl+Enter для отправки, Shift+Enter для новой строки)
  if (questionInput) {
    questionInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey && !e.altKey) {
        // Отправка по Enter (если настроено)
        // e.preventDefault();
        // chatForm.dispatchEvent(new Event('submit'));
      } else if (e.key === 'Enter' && e.ctrlKey) {
        // Отправка по Ctrl+Enter
        e.preventDefault();
        chatForm.dispatchEvent(new Event('submit'));
      }
      // Shift+Enter - новая строка (работает по умолчанию)
    });
  }
});