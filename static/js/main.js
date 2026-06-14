// Глобальные переменные
let currentFileData = null;
let currentFilename = null;
let isJsonMode = false;
let availableFields = [];
let dataSample = [];
let currentResultId = null;
let currentChunks = null;
let totalChunks = 0;

// Логирование действий пользователя
function logAction(message, type = 'info') {
    const logContent = document.getElementById('logContent');
    if (logContent) {
        const timestamp = new Date().toLocaleTimeString();
        const logEntry = `[${timestamp}] ${message}\n`;
        logContent.innerHTML += `<span class="text-${type}">${logEntry}</span>`;
        logContent.scrollTop = logContent.scrollHeight;
    }
}

// Обработка загрузки файла
document.addEventListener('DOMContentLoaded', function() {
    const uploadForm = document.getElementById('uploadForm');
    if (uploadForm) {
        uploadForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const fileInput = document.getElementById('file');
            const file = fileInput.files[0];
            
            if (!file) {
                alert('Пожалуйста, выберите файл!');
                return;
            }
            
            // Показываем прогресс и лог
            document.querySelector('.progress').style.display = 'block';
            document.getElementById('logArea').style.display = 'block';
            document.getElementById('resultSection').style.display = 'none';
            document.getElementById('mappingSection').style.display = 'none';
            
            logAction('Начало загрузки файла...', 'info');
            
            // Создаем FormData для отправки файла
            const formData = new FormData();
            formData.append('file', file);
            
            // Отправляем файл на сервер
            fetch('/upload', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    logAction(`✅ ${data.message}`, 'success');
                    logAction(`Размер файла: ${(data.size/1024).toFixed(2)} KB`, 'info');
                    
                    // Сохраняем данные
                    currentFileData = data.file_data;
                    currentFilename = data.filename;
                    isJsonMode = data.is_json_mode;
                    availableFields = data.fields || [];
                    dataSample = data.sample || [];
                    currentResultId = data.result_id;
                    
                    if (isJsonMode && availableFields.length > 0) {
                        // Показываем секцию настройки полей
                        showMappingSection();
                    } else {
                        // Прямо переходим к обработке
                        processFileDirectly();
                    }
                } else {
                    logAction(`❌ Ошибка: ${data.error}`, 'error');
                    document.querySelector('.progress').style.display = 'none';
                }
            })
            .catch(error => {
                logAction(`❌ Ошибка сети: ${error}`, 'error');
                document.querySelector('.progress').style.display = 'none';
            });
        });
    }
});

// Показ секции настройки полей
function showMappingSection() {
    document.querySelector('.progress').style.display = 'none';
    
    const mappingSection = document.getElementById('mappingSection');
    if (mappingSection) {
        mappingSection.style.display = 'block';
        
        // Заполняем поля
        const fieldSelects = mappingSection.querySelectorAll('select');
        fieldSelects.forEach(select => {
            select.innerHTML = '<option value="">-- Не выбрано --</option>';
            if (availableFields && availableFields.length > 0) {
                availableFields.forEach(field => {
                    const option = document.createElement('option');
                    option.value = field;
                    option.textContent = field;
                    select.appendChild(option);
                });
            }
        });
        
        // Заполняем предпросмотр
        updatePreview();
    }
    
    logAction('Настройте поля для обработки', 'info');
}

// Обновление предпросмотра
function updatePreview() {
    const previewDiv = document.getElementById('mappingPreview');
    if (!previewDiv || !dataSample || dataSample.length === 0) return;
    
    const categoryField = document.getElementById('categoryField')?.value || '';
    const contentField = document.getElementById('contentField')?.value || '';
    const atomicField = document.getElementById('atomicField')?.value || '';
    
    const item = dataSample[0];
    const category = categoryField && item[categoryField] ? item[categoryField] : 'General';
    
    let previewStr = '';
    if (atomicField && item[atomicField] && Array.isArray(item[atomicField]) && item[atomicField].length > 0) {
        const subItem = item[atomicField][0];
        const baseText = contentField && item[contentField] ? 
            String(item[contentField]).substring(0, 60) : '';
        const baseTextDisplay = baseText + (contentField && item[contentField] && String(item[contentField]).length > 60 ? '...' : '');
        previewStr = `Атомизация:\n{ "cat": "${category}", "text": "${baseTextDisplay} - это \\"${subItem}\\"" }`;
    } else {
        const content = contentField && item[contentField] ? 
            String(item[contentField]).substring(0, 80) : 'Нет текста';
        const contentDisplay = content + (contentField && item[contentField] && String(item[contentField]).length > 80 ? '...' : '');
        previewStr = `Обычный:\n{ "cat": "${category}", "text": "${contentDisplay}" }`;
    }
    
    previewDiv.textContent = previewStr;
}

// Автоматическая настройка полей
function autoConfigureFields() {
    if (!availableFields || availableFields.length === 0) return;
    
    // Простые правила для автоматического сопоставления
    const keywords = {
        "categoryField": ["name", "category", "group", "type", "title", "label", "категория", "название"],
        "contentField": ["description", "text", "body", "content", "prompt", "desc", "описание", "текст"],
        "atomicField": ["list", "tags", "items", "sub", "options", "categories", "second", "список", "теги"]
    };
    
    Object.keys(keywords).forEach(key => {
        const selectId = key === "categoryField" ? "categoryField" : 
                        key === "contentField" ? "contentField" : "atomicField";
        const select = document.getElementById(selectId);
        if (select) {
            // Ищем подходящее поле
            let found = false;
            for (const kw of keywords[key]) {
                for (const field of availableFields) {
                    if (field.toLowerCase().includes(kw.toLowerCase())) {
                        select.value = field;
                        found = true;
                        break;
                    }
                }
                if (found) break;
            }
        }
    });
    
    updatePreview();
    logAction('Поля настроены автоматически', 'info');
}

// Автоматическая настройка параметров чанкинга
function autoTuneSettings() {
    const mapping = {
        category_field: document.getElementById('categoryField')?.value || null,
        content_field: document.getElementById('contentField')?.value || null,
        atomic_field: document.getElementById('atomicField')?.value || null
    };
    
    fetch('/auto_tune', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            sample: dataSample,
            mapping: mapping
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            document.getElementById('chunkSize').value = data.settings.size;
            document.getElementById('chunkOverlap').value = data.settings.overlap;
            logAction(`⚙️ Параметры авто-настроены: размер=${data.settings.size}, перекрытие=${data.settings.overlap}`, 'info');
        } else {
            logAction(`❌ Ошибка авто-настройки: ${data.error}`, 'error');
        }
    })
    .catch(error => {
        logAction(`❌ Ошибка сети при авто-настройке: ${error}`, 'error');
    });
}

// Применить настройки полей и выполнить чанкинг
function applyMapping() {
    const mapping = {
        category_field: document.getElementById('categoryField')?.value || null,
        content_field: document.getElementById('contentField')?.value || null,
        atomic_field: document.getElementById('atomicField')?.value || null
    };
    
    // Проверяем, что хотя бы одно поле выбрано
    if (!mapping.category_field && !mapping.content_field && !mapping.atomic_field) {
        alert('Пожалуйста, выберите хотя бы одно поле!');
        return;
    }
    
    logAction('Настройки полей применены', 'success');
    document.getElementById('mappingSection').style.display = 'none';
    
    // Выполняем чанкинг
    performChunking(mapping);
}

// Выполнение чанкинга
function performChunking(mapping) {
    document.querySelector('.progress').style.display = 'block';
    logAction('Начало чанкинга...', 'info');
    
    const template = document.getElementById('template').value || 'universal';
    const chunkSize = parseInt(document.getElementById('chunkSize').value) || 800;
    const chunkOverlap = parseInt(document.getElementById('chunkOverlap').value) || 80;
    
    fetch('/chunk', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            result_id: currentResultId,
            mapping: mapping,
            template: template,
            chunk_size: chunkSize,
            chunk_overlap: chunkOverlap
        })
    })
    .then(response => response.json())
    .then(data => {
        document.querySelector('.progress').style.display = 'none';
        
        if (data.success) {
            logAction(`✅ ${data.message}`, 'success');
            currentChunks = data.chunks;
            totalChunks = data.total_chunks;
            currentResultId = data.result_id;
            showResults();
        } else {
            logAction(`❌ Ошибка чанкинга: ${data.error}`, 'error');
        }
    })
    .catch(error => {
        document.querySelector('.progress').style.display = 'none';
        logAction(`❌ Ошибка сети при чанкинге: ${error}`, 'error');
    });
}

// Обработка файла напрямую (для текстовых файлов)
function processFileDirectly() {
    document.querySelector('.progress').style.display = 'none';
    logAction('Файл будет обработан как текст', 'info');
    
    // Для текстовых файлов используем простое сопоставление
    const mapping = {
        content_field: 'text',
        category_field: null,
        atomic_field: null
    };
    
    performChunking(mapping);
}

// Показ результатов
function showResults() {
    document.getElementById('resultSection').style.display = 'block';
    document.getElementById('chunkCount').textContent = totalChunks;
    
    // Создаем предпросмотр первых нескольких чанков
    const preview = document.getElementById('previewContent');
    preview.innerHTML = '';
    
    if (currentChunks && currentChunks.length > 0) {
        const previewChunks = currentChunks.slice(0, Math.min(5, currentChunks.length));
        
        previewChunks.forEach((chunk, index) => {
            const chunkDiv = document.createElement('div');
            chunkDiv.className = 'alert alert-light';
            chunkDiv.innerHTML = `
                <strong>Чанк #${index + 1}:</strong><br>
                Категория: ${chunk.category || chunk.metadata?.category || 'N/A'}<br>
                Текст: ${chunk.content || chunk.text || ''}<br>
            `;
            preview.appendChild(chunkDiv);
        });
        
        if (currentChunks.length > 5) {
            const moreDiv = document.createElement('div');
            moreDiv.className = 'alert alert-info';
            moreDiv.innerHTML = `... и еще ${currentChunks.length - 5} чанков`;
            preview.appendChild(moreDiv);
        }
    }
}

// Скачивание результатов
function downloadResult(format) {
    if (!currentResultId) {
        alert('Нет результатов для скачивания!');
        return;
    }
    
    // Определяем режим (для RAG или для чтения)
    const forRag = document.getElementById('saveModeRag')?.checked || false;
    
    logAction(`📥 Запрос на сохранение в формате ${format.toUpperCase()} (${forRag ? 'Для БЗ' : 'Для чтения'})`, 'info');
    
    fetch(`/export/${format}/${currentResultId}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            for_rag: forRag
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            logAction(`✅ ${data.message}`, 'success');
            // Создаем ссылку для скачивания
            const downloadUrl = `/download/${data.filename}`;
            const link = document.createElement('a');
            link.href = downloadUrl;
            link.download = data.filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        } else {
            logAction(`❌ Ошибка экспорта: ${data.error}`, 'error');
            alert(`Ошибка: ${data.error}`);
        }
    })
    .catch(error => {
        logAction(`❌ Ошибка сети при экспорте: ${error}`, 'error');
        alert(`Ошибка сети: ${error}`);
    });
}

// Обновление настроек в реальном времени
document.addEventListener('DOMContentLoaded', function() {
    const presetSelect = document.getElementById('preset');
    if (presetSelect) {
        presetSelect.addEventListener('change', function() {
            const preset = this.value;
            const presets = {
                'auto': {size: 800, overlap: 80},
                'facts': {size: 400, overlap: 40},
                'balanced': {size: 800, overlap: 80},
                'context': {size: 1200, overlap: 150}
            };
            
            if (presets[preset]) {
                document.getElementById('chunkSize').value = presets[preset].size;
                document.getElementById('chunkOverlap').value = presets[preset].overlap;
                logAction(`⚙️ Пресет изменен на: ${preset}`, 'info');
                
                // Если авто-настройка, применяем сразу
                if (preset === 'auto' && dataSample.length > 0) {
                    autoTuneSettings();
                }
            }
        });
    }
    
    // Обновление предпросмотра при изменении полей
    const mappingFields = ['categoryField', 'contentField', 'atomicField'];
    mappingFields.forEach(fieldId => {
        const field = document.getElementById(fieldId);
        if (field) {
            field.addEventListener('change', updatePreview);
        }
    });
});
