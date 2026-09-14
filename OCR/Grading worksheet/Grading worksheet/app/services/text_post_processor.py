# """
# Text Post-Processing Module for OCR Results
#
# This module provides advanced text cleaning, correction, and enhancement
# for OCR results, with a focus on improving accuracy of handwritten text.
# """
#
# import re
# import logging
# from typing import List, Tuple, Dict, Any, Optional
# from spellchecker import SpellChecker
# import language_tool_python
# import nltk
# from nltk.tokenize import word_tokenize, sent_tokenize
# from nltk.corpus import wordnet
#
# # Download required NLTK data
# try:
#     nltk.data.find('tokenizers/punkt')
#     nltk.data.find('corpora/wordnet')
# except LookupError:
#     nltk.download('punkt')
#     nltk.download('wordnet')
#     nltk.download('averaged_perceptron_tagger')
#
# logger = logging.getLogger(__name__)
#
# class TextPostProcessor:
#     """Handles post-processing of OCR text to improve accuracy and readability."""
#
#     def __init__(self, language: str = 'en'):
#         """Initialize the text post-processor.
#
#         Args:
#             language: Language code for spell checking and grammar correction
#         """
#         self.language = language
#         self.spell = SpellChecker(language=language)
#         self.grammar_tool = language_tool_python.LanguageTool(language)
#
#         # Common OCR error mappings
#         self.ocr_error_mapping = {
#             '|': 'I', '0': 'O', '1': 'I', '5': 'S', '8': 'B',
#             'vv': 'w', 'VV': 'W', 'rn': 'm', 'cl': 'd', 'ij': 'n',
#             # Add more common OCR errors as needed
#         }
#
#         # Compile regex patterns
#         self.whitespace_regex = re.compile(r'\s+')
#         self.non_word_regex = re.compile(r'[^\w\s]')
#
#     def clean_text(self, text: str) -> str:
#         """Basic text cleaning and normalization."""
#         if not text:
#             return text
#
#         # Convert to string if not already
#         text = str(text)
#
#         # Normalize whitespace
#         text = self.whitespace_regex.sub(' ', text).strip()
#
#         # Fix common OCR errors
#         for error, correction in self.ocr_error_mapping.items():
#             text = text.replace(error, correction)
#
#         return text
#
#     def correct_spelling(self, text: str) -> str:
#         """Correct spelling errors in the text."""
#         if not text.strip():
#             return text
#
#         # Tokenize the text
#         words = word_tokenize(text)
#
#         # Correct each word
#         corrected_words = []
#         for word in words:
#             # Skip empty words
#             if not word.strip():
#                 continue
#
#             # Skip words that are likely not misspelled (numbers, proper nouns, etc.)
#             if (word[0].isupper() or  # Proper nouns
#                 any(c.isdigit() for c in word) or  # Numbers
#                 len(word) <= 2):  # Very short words
#                 corrected_words.append(word)
#                 continue
#
#             # Get the most likely correction
#             corrected = self.spell.correction(word)
#             corrected_words.append(corrected if corrected else word)
#
#         return ' '.join(corrected_words)
#
#     def correct_grammar(self, text: str) -> str:
#         """Correct grammar and punctuation in the text."""
#         if not text.strip():
#             return text
#
#         try:
#             # Use language-tool for grammar correction
#             matches = self.grammar_tool.check(text)
#
#             # Apply corrections in reverse order to avoid offset issues
#             for match in reversed(matches):
#                 if match.replacements:
#                     start = match.offset
#                     end = match.offset + match.errorLength
#                     text = text[:start] + match.replacements[0] + text[end:]
#
#             return text
#         except Exception as e:
#             logger.warning(f"Grammar correction failed: {e}")
#             return text
#
#     def post_process(self, text: str,
#                     correct_spelling: bool = True,
#                     correct_grammar: bool = True) -> str:
#         """Apply all post-processing steps to the text.
#
#         Args:
#             text: Input text to process
#             correct_spelling: Whether to correct spelling
#             correct_grammar: Whether to correct grammar
#
#         Returns:
#             Processed text
#         """
#         if not text:
#             return ""
#
#         # Clean the text
#         processed = self.clean_text(text)
#
#         # Apply spelling correction if enabled
#         if correct_spelling:
#             processed = self.correct_spelling(processed)
#
#         # Apply grammar correction if enabled
#         if correct_grammar:
#             processed = self.correct_grammar(processed)
#
#         return processed
#
#     def process_ocr_results(self, results: List[Dict[str, Any]],
#                           correct_spelling: bool = True,
#                           correct_grammar: bool = True) -> List[Dict[str, Any]]:
#         """Process OCR results with text and bounding boxes.
#
#         Args:
#             results: List of dictionaries with 'text' and 'bbox' keys
#             correct_spelling: Whether to correct spelling
#             correct_grammar: Whether to correct grammar
#
#         Returns:
#             List of processed results
#         """
#         processed_results = []
#
#         for result in results:
#             original_text = result.get('text', '')
#             processed_text = self.post_process(
#                 original_text,
#                 correct_spelling=correct_spelling,
#                 correct_grammar=correct_grammar
#             )
#
#             # Create a new result with processed text
#             processed_result = result.copy()
#             processed_result['text'] = processed_text
#             processed_result['original_text'] = original_text
#
#             processed_results.append(processed_result)
#
#         return processed_results
