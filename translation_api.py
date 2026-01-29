# translation_api.py
import aiohttp
from typing import List, Optional
import asyncio
import os


class TranslationAPI:
    """번역 API 기본 클래스"""
    
    def __init__(self, api_url: str = "http://localhost:8000"):
        self.api_url = api_url.rstrip('/')
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def translate(
        self, 
        text: str, 
        source_lang: str = "en", 
        target_lang: str = "ko"
    ) -> str:
        """단일 텍스트 번역"""
        if not text or not text.strip():
            return text
        
        try:
            async with self.session.post(
                f"{self.api_url}/translate",
                json={
                    "text": text,
                    "source_lang": source_lang,
                    "target_lang": target_lang
                },
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get('translation', text)
                else:
                    print(f"Translation API error: {response.status}")
                    return text
        except Exception as e:
            print(f"Translation error: {e}")
            return text
    
    async def batch_translate(
        self, 
        texts: List[str], 
        source_lang: str = "en", 
        target_lang: str = "ko",
        batch_size: int = 50
    ) -> List[str]:
        """배치 번역"""
        if not texts:
            return []
        
        non_empty_indices = [i for i, text in enumerate(texts) if text and text.strip()]
        non_empty_texts = [texts[i] for i in non_empty_indices]
        
        if not non_empty_texts:
            return texts
        
        translated = []
        
        for i in range(0, len(non_empty_texts), batch_size):
            batch = non_empty_texts[i:i + batch_size]
            
            try:
                async with self.session.post(
                    f"{self.api_url}/translate/batch",
                    json={
                        "texts": batch,
                        "source_lang": source_lang,
                        "target_lang": target_lang
                    },
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        translated.extend(result.get('translations', batch))
                    else:
                        print(f"Batch translation error: {response.status}")
                        translated.extend(batch)
            except Exception as e:
                print(f"Batch translation error: {e}")
                translated.extend(batch)
            
            await asyncio.sleep(0.1)
        
        result = list(texts)
        for idx, trans_text in zip(non_empty_indices, translated):
            result[idx] = trans_text
        
        return result


class OpenAITranslationAPI(TranslationAPI):
    """OpenAI GPT를 사용한 번역 API"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1"
    ):
        """
        Args:
            api_key: OpenAI API 키 (None이면 환경변수 OPENAI_API_KEY 사용)
            model: 사용할 모델 (gpt-4o, gpt-4o-mini, gpt-4-turbo, gpt-3.5-turbo 등)
            base_url: API 베이스 URL
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI API key is required. "
                "Set OPENAI_API_KEY environment variable or pass api_key parameter."
            )
        
        self.model = model
        self.base_url = base_url.rstrip('/')
        self.session: Optional[aiohttp.ClientSession] = None
        
        print(f"Using OpenAI model: {self.model}")
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def get_language_name(self, lang_code: str) -> str:
        """언어 코드를 전체 이름으로 변환"""
        lang_map = {
            'en': 'English',
            'ko': 'Korean',
            'ja': 'Japanese',
            'zh': 'Chinese',
            'es': 'Spanish',
            'fr': 'French',
            'de': 'German',
            'ru': 'Russian',
            'it': 'Italian',
            'pt': 'Portuguese'
        }
        return lang_map.get(lang_code.lower(), lang_code)
    
    async def translate(
        self,
        text: str,
        source_lang: str = "en",
        target_lang: str = "ko"
    ) -> str:
        """단일 텍스트 번역"""
        if not text or not text.strip():
            return text
        
        source_name = self.get_language_name(source_lang)
        target_name = self.get_language_name(target_lang)
        
        system_prompt = (
            f"You are a professional translator. "
            f"Translate the following text from {source_name} to {target_name}. "
            f"Preserve the original meaning, tone, and style. "
            f"Only output the translation without any explanations."
        )
        
        try:
            async with self.session.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": text}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 2000
                },
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    translated = result['choices'][0]['message']['content'].strip()
                    return translated
                else:
                    error_text = await response.text()
                    print(f"OpenAI API error {response.status}: {error_text}")
                    return text
                    
        except Exception as e:
            print(f"Translation error: {e}")
            return text
    
    async def batch_translate(
        self,
        texts: List[str],
        source_lang: str = "en",
        target_lang: str = "ko",
        batch_size: int = 20  # GPT는 더 작은 배치 사용
    ) -> List[str]:
        """배치 번역 - 여러 텍스트를 한 번에 처리"""
        if not texts:
            return []
        
        non_empty_indices = [i for i, text in enumerate(texts) if text and text.strip()]
        non_empty_texts = [texts[i] for i in non_empty_indices]
        
        if not non_empty_texts:
            return texts
        
        source_name = self.get_language_name(source_lang)
        target_name = self.get_language_name(target_lang)
        
        translated = []
        
        for i in range(0, len(non_empty_texts), batch_size):
            batch = non_empty_texts[i:i + batch_size]
            
            # 배치를 JSON 형식으로 만들기
            batch_text = "\n---\n".join([f"[{idx}] {text}" for idx, text in enumerate(batch)])
            
            system_prompt = (
                f"You are a professional translator. "
                f"Translate each text from {source_name} to {target_name}. "
                f"Each text is prefixed with [number]. "
                f"Return translations in the same format: [number] translated_text. "
                f"Preserve original meaning, tone, and style. "
                f"Maintain the exact same number of entries."
                f"Don't translate things like 2034E, 11.5x, 0.6x, FY25E EPS, P/E, EPS(net), EV/Revenue, NYSE, NASDAQ, but just print out the original text."
            )
            
            try:
                async with self.session.post(
                    f"{self.base_url}/chat/completions",
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": batch_text}
                        ],
                        "temperature": 0.3,
                        "max_tokens": 4000
                    },
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        translated_text = result['choices'][0]['message']['content'].strip()
                        
                        # 결과 파싱
                        batch_translations = self.parse_batch_response(translated_text, len(batch))
                        
                        if len(batch_translations) == len(batch):
                            translated.extend(batch_translations)
                        else:
                            # 파싱 실패 시 개별 번역으로 폴백
                            print(f"  Warning: Batch parsing failed, falling back to individual translation")
                            for text in batch:
                                trans = await self.translate(text, source_lang, target_lang)
                                translated.append(trans)
                    else:
                        error_text = await response.text()
                        print(f"  Batch translation error {response.status}: {error_text}")
                        translated.extend(batch)
                        
            except Exception as e:
                print(f"  Batch translation error: {e}")
                # 실패 시 개별 번역 시도
                for text in batch:
                    trans = await self.translate(text, source_lang, target_lang)
                    translated.append(trans)
            
            # API rate limit 방지
            await asyncio.sleep(0.5)
        
        # 원래 위치에 번역 결과 매핑
        result = list(texts)
        for idx, trans_text in zip(non_empty_indices, translated):
            result[idx] = trans_text
        
        return result
    
    def parse_batch_response(self, response_text: str, expected_count: int) -> List[str]:
        """배치 응답 파싱"""
        lines = response_text.split('\n')
        translations = []
        
        for line in lines:
            line = line.strip()
            if not line or line == '---':
                continue
            
            # [숫자] 형식 제거
            if line.startswith('[') and ']' in line:
                # [0] 번역문 -> 번역문
                closing_bracket = line.index(']')
                translation = line[closing_bracket + 1:].strip()
                translations.append(translation)
            else:
                translations.append(line)
        
        return translations[:expected_count]


class DummyTranslationAPI(TranslationAPI):
    """테스트용 더미 번역 API"""
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
    
    async def translate(
        self, 
        text: str, 
        source_lang: str = "en", 
        target_lang: str = "ko"
    ) -> str:
        """더미 번역"""
        if not text or not text.strip():
            return text
        await asyncio.sleep(0.001)
        return f"[번역] {text}"
    
    async def batch_translate(
        self, 
        texts: List[str], 
        source_lang: str = "en", 
        target_lang: str = "ko",
        batch_size: int = 50
    ) -> List[str]:
        """더미 배치 번역"""
        await asyncio.sleep(0.01)
        return [f"[번역] {text}" if text and text.strip() else text for text in texts]