# processors/file_processor.py
import os
import json
import re
from typing import List, Dict, Any, Optional

# Проверка доступности библиотек
try:
    import docx
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

try:
    import pdfplumber
    PDF_INPUT_AVAILABLE = True
except ImportError:
    PDF_INPUT_AVAILABLE = False

class FileProcessor:
    """Класс для обработки различных форматов файлов"""
    
    def __init__(self):
        self.is_json_mode = False
        self.raw_data_sample = None
        self.available_fields = []
        self.source_filename = ""
        
    def process_file(self, file_path: str, filename: str) -> Dict[str, Any]:
        """
        Основной метод обработки файла
        Возвращает словарь с результатами обработки
        """
        self.source_filename = filename
        ext = os.path.splitext(filename)[1].lower()
        
        try:
            if ext == '.json':
                return self._process_json_file(file_path)
            elif ext == '.pdf':
                return self._process_pdf_file(file_path)
            elif ext in ['.txt', '.docx']:
                return self._process_text_file(file_path, ext)
            else:
                raise ValueError(f"Неподдерживаемый формат файла: {ext}")
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'data': None,
                'is_json_mode': False
            }
    
    def _process_json_file(self, file_path: str) -> Dict[str, Any]:
        """Обработка JSON файлов"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Если это словарь, ищем массив объектов
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                        data = v
                        break
            
            # Проверяем, что это массив объектов
            if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                self.available_fields = list(data[0].keys()) if data else []
                self.raw_data_sample = data[:10]  # Берем только первые 10 элементов для примера
                self.is_json_mode = True
                
                return {
                    'success': True,
                    'data': data,
                    'is_json_mode': True,
                    'fields': self.available_fields,
                    'sample': self.raw_data_sample,
                    'message': f"JSON найден. Поля: {', '.join(self.available_fields)}"
                }
            else:
                # Если это не массив объектов, обрабатываем как текст
                json_str = json.dumps(data, ensure_ascii=False, indent=2)
                return self._process_as_text(json_str)
                
        except Exception as e:
            return {
                'success': False,
                'error': f"Ошибка обработки JSON: {str(e)}",
                'data': None,
                'is_json_mode': False
            }
    
    def _process_pdf_file(self, file_path: str) -> Dict[str, Any]:
        """Обработка PDF файлов"""
        if not PDF_INPUT_AVAILABLE:
            return {
                'success': False,
                'error': "Библиотека pdfplumber не установлена",
                'data': None,
                'is_json_mode': False
            }
        
        try:
            # Извлекаем текст из PDF
            text_content = ""
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        text_content += text + "\n"
            
            # Пытаемся найти JSON в тексте
            json_data = self._try_extract_json_from_text(text_content)
            if json_data and json_data.get('success'):
                return json_data
            else:
                # Обрабатываем как обычный текст
                return self._process_as_text(text_content)
                
        except Exception as e:
            return {
                'success': False,
                'error': f"Ошибка обработки PDF: {str(e)}",
                'data': None,
                'is_json_mode': False
            }
    
    def _process_text_file(self, file_path: str, ext: str) -> Dict[str, Any]:
        """Обработка текстовых файлов (TXT, DOCX)"""
        try:
            text_content = ""
            if ext == '.docx':
                if not DOCX_AVAILABLE:
                    return {
                        'success': False,
                        'error': "Библиотека python-docx не установлена",
                        'data': None,
                        'is_json_mode': False
                    }
                
                doc = docx.Document(file_path)
                text_content = "\n".join([p.text for p in doc.paragraphs])
            else:
                with open(file_path, 'r', encoding='utf-8') as f:
                    text_content = f.read()
            
            # Пытаемся найти JSON в тексте
            json_data = self._try_extract_json_from_text(text_content)
            if json_data and json_data.get('success'):
                return json_data
            else:
                # Обрабатываем как обычный текст
                return self._process_as_text(text_content)
                
        except Exception as e:
            return {
                'success': False,
                'error': f"Ошибка обработки текстового файла: {str(e)}",
                'data': None,
                'is_json_mode': False
            }
    
    def _process_as_text(self, text_content: str) -> Dict[str, Any]:
        """Обработка как обычного текста"""
        if not text_content.strip():
            return {
                'success': False,
                'error': "Файл пуст",
                'data': None,
                'is_json_mode': False
            }
        
        # Создаем структуру для текстового режима
        data = [{"text": text_content.strip()}]
        
        return {
            'success': True,
            'data': data,
            'is_json_mode': False,
            'message': "Файл обработан как обычный текст",
            'fields': ['text']
        }
    
    def _try_extract_json_from_text(self, text_content: str) -> Optional[Dict[str, Any]]:
        """Попытка извлечь JSON из текста"""
        if not text_content or not text_content.strip():
            return None
            
        # Ищем начало JSON массива или объекта
        start_brace = text_content.find('[')
        start_curly = text_content.find('{')
        
        # Определяем, что встречается первым
        if start_brace == -1 and start_curly == -1:
            return None
        elif start_brace == -1:
            start_pos = start_curly
        elif start_curly == -1:
            start_pos = start_brace
        else:
            start_pos = min(start_brace, start_curly)
        
        if start_pos == -1:
            return None
        
        # Берем текст с найденной позиции
        clean_text = text_content[start_pos:].strip()
        
        # Попытка 1: Прямой парсинг
        try:
            data = json.loads(clean_text)
            if self._is_valid_json_data(data):
                return self._format_json_result(data)
        except:
            pass
        
        # Попытка 2: Удаление переносов и лишних символов
        # Удаляем переносы строк, табуляции и лишние пробелы
        candidate = re.sub(r'[\n\r\t]+', ' ', clean_text)
        # Удаляем множественные пробелы
        candidate = re.sub(r'\s+', ' ', candidate)
        # Убираем лишние символы в конце
        end_bracket = candidate.rfind(']')
        end_curly = candidate.rfind('}')
        end_pos = max(end_bracket, end_curly)
        if end_pos != -1:
            candidate = candidate[:end_pos+1]
        
        try:
            data = json.loads(candidate)
            if self._is_valid_json_data(data):
                return self._format_json_result(data)
        except:
            pass
        
        # Попытка 3: Более агрессивная очистка
        try:
            # Удаляем все до первого [ или {
            first_bracket = candidate.find('[')
            first_curly = candidate.find('{')
            if first_bracket != -1 or first_curly != -1:
                if first_bracket == -1:
                    clean_start = first_curly
                elif first_curly == -1:
                    clean_start = first_bracket
                else:
                    clean_start = min(first_bracket, first_curly)
                
                if clean_start != -1:
                    candidate = candidate[clean_start:]
                    
                    # Ищем конец
                    if candidate.startswith('['):
                        end_pos = candidate.rfind(']')
                    else:
                        end_pos = candidate.rfind('}')
                    
                    if end_pos != -1:
                        candidate = candidate[:end_pos+1]
                        
                        data = json.loads(candidate)
                        if self._is_valid_json_data(data):
                            return self._format_json_result(data)
        except:
            pass
        
        return None
    
    def _is_valid_json_data(self, data) -> bool:
        """Проверка, что данные являются валидными для обработки"""
        if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
            return True
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                    return True
            # Даже один объект можно обработать
            return len(data) > 0
        return False
    
    def _format_json_result(self, data) -> Dict[str, Any]:
        """Форматирование результата JSON обработки"""
        if isinstance(data, dict):
            # Ищем массив объектов в словаре
            for k, v in data.items():
                if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                    data = v
                    break
            else:
                # Если массив не найден, оборачиваем в список
                data = [data]
        
        if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
            fields = list(data[0].keys()) if data else []
            sample = data[:10]  # Берем первые 10 элементов
            
            return {
                'success': True,
                'data': data,
                'is_json_mode': True,
                'fields': fields,
                'sample': sample,
                'message': f"JSON найден. Поля: {', '.join(fields)}"
            }
        
        return None

# Глобальный экземпляр процессора
file_processor = FileProcessor()
