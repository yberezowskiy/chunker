# processors/chunker.py
from langchain_text_splitters import RecursiveCharacterTextSplitter
from typing import List, Dict, Any

class RAGChunker:
    """Класс для чанкинга данных"""
    
    def __init__(self):
        self.templates = {
            "universal": "🏆 Универсальный (LangChain/Pinecone)",
            "speech_sense": "🤖 Speech Sense (Строгий парсинг)",
            "flat": "📄 Плоский текст (Ключевые слова)"
        }
        
        self.template_descs = {
            "universal": "Связный текст + мета-данные. Идеально для векторного поиска.",
            "speech_sense": "Конструкция 'Текст — это Список'. Для систем со строгим синтаксисом.",
            "flat": "Просто текст. Минимум структуры, максимум ключевых слов."
        }
        
        self.presets = {
            "auto": {"size": 800, "overlap": 80},
            "facts": {"size": 400, "overlap": 40},
            "balanced": {"size": 800, "overlap": 80},
            "context": {"size": 1200, "overlap": 150}
        }
        
        self.preset_descs = {
            "auto": "Программа сама проанализирует длину текста и подберет размер.",
            "facts": "Мелкие чанки (~400 симв). Для коротких ответов.",
            "balanced": "Средние чанки (~800 симв). Золотая середина.",
            "context": "Крупные чанки (~1200+ симв). Для сложных документов."
        }
    
    def normalize_and_chunk(self, data: List[Dict], mapping_config: Dict[str, str], 
                          template_type: str, chunk_size: int, chunk_overlap: int,
                          source_filename: str) -> List[Dict]:
        """
        Основной метод чанкинга
        """
        chunks = []
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        
        total_items = len(data)
        
        for idx, item in enumerate(data):
            category = str(item.get(mapping_config.get("category_field"), "Unknown")) \
                      if mapping_config.get("category_field") else "General"
            
            base_text = str(item.get(mapping_config.get("content_field"), "")).strip() \
                       if mapping_config.get("content_field") else ""
            
            sub_list = []
            atomic_field = mapping_config.get("atomic_field")
            if atomic_field and atomic_field in item and isinstance(item[atomic_field], list):
                sub_list = item[atomic_field]
            
            items_to_process = []
            
            if not sub_list:
                items_to_process.append({"category": category, "content": base_text})
            else:
                if template_type == "speech_sense":
                    for sub_item in sub_list:
                        sub_str = str(sub_item).strip()
                        if not sub_str:
                            continue
                        txt = f"{base_text} - это \"{sub_str}\"" if base_text else f"Элемент: \"{sub_str}\""
                        items_to_process.append({"category": category, "content": txt})
                
                elif template_type == "universal":
                    for sub_item in sub_list:
                        sub_str = str(sub_item).strip()
                        if not sub_str:
                            continue
                        txt = f"В категории '{category}': {base_text}. Аспект: {sub_str}." \
                              if base_text else f"Аспект '{category}': {sub_str}."
                        items_to_process.append({"category": category, "content": txt})
                
                elif template_type == "flat":
                    list_str = ", ".join([str(s) for s in sub_list])
                    txt = f"{base_text} {list_str}" if base_text else list_str
                    items_to_process.append({"category": category, "content": txt})
            
            for unit in items_to_process:
                if not unit["content"].strip():
                    continue
                
                split_texts = splitter.split_text(unit["content"])
                for i, chunk_text in enumerate(split_texts):
                    chunk_obj = {}
                    
                    if template_type == "universal":
                        chunk_obj = {
                            "content": chunk_text,
                            "metadata": {
                                "category": unit["category"],
                                "source": source_filename,
                                "chunk_id": f"{idx}_{i}"
                            }
                        }
                    elif template_type == "speech_sense":
                        chunk_obj = {
                            "category": unit["category"],
                            "content": chunk_text,
                            "chunk_id": f"{idx}_{i}"
                        }
                    else:  # flat
                        chunk_obj = {
                            "text": chunk_text,
                            "category": unit["category"]
                        }
                    
                    chunks.append(chunk_obj)
        
        return chunks
    
    def auto_tune_settings(self, data_sample: List[Dict], mapping_config: Dict[str, str]) -> Dict[str, int]:
        """
        Автоматическая настройка параметров чанкинга
        """
        if not data_sample:
            return {"size": 800, "overlap": 80}
        
        content_key = mapping_config.get("content_field", "description")
        lengths = []
        
        for item in data_sample[:10]:  # Берем первые 10 элементов
            if content_key in item:
                text = str(item[content_key])
                atomic_key = mapping_config.get("atomic_field")
                
                if atomic_key and atomic_key in item and isinstance(item[atomic_key], list) and item[atomic_key]:
                    avg_sub_len = sum(len(str(s)) for s in item[atomic_key]) / len(item[atomic_key])
                    lengths.append(len(text) + avg_sub_len + 20)
                else:
                    lengths.append(len(text))
        
        if not lengths:
            lengths = [500]
        
        avg_len = sum(lengths) / len(lengths)
        
        if avg_len < 300:
            return {"size": 400, "overlap": 40}  # facts
        elif avg_len > 1500:
            return {"size": 1000, "overlap": 150}  # context
        else:
            return {"size": 800, "overlap": 80}  # balanced
