# TODO: reuse players for other codename variants, e.g. Duet?
# TODO: check whether target is only a number -> validation error, not ignoring targets!
# TODO: check whether clue is *only* a number
# TODO: ignore wrong guesses/targets first, before inferring amount of words!

from typing import Dict, List
import re, random, string, nltk

from clemgame.clemgame import Player
from .constants import *
from .validation_errors import *

nltk.download('wordnet', quiet=True)
EN_LEMMATIZER = nltk.stem.WordNetLemmatizer()

def find_line_starting_with(prefix, lines):
    for line in lines:
        if line.startswith(prefix):
            return line
        
class ClueGiver(Player):
    def __init__(self, model_name: str, flags: Dict[str, bool]):
        super().__init__(model_name)
        self.clue_prefix: str = "CLUE: "
        self.target_prefix: str = "TARGETS: "
        self.clue: str = 'clue'
        self.number_of_targets: int = 2
        self.targets: List[str] = ['target', 'word']
        self.retries: int = 0
        self.flags = flags
        self.flags_engaged = {key: 0 for key, value in flags.items()}

    def _custom_response(self, history, turn) -> str:
        prompt = history[-1]["content"]
        match = re.search(r"team words are: (.*)\.", prompt)
        if match != None:
            # Player was actually prompted (otherwise it was reprompted and the team_words stay the same)
            team_words = match.group(1)
            team_words = team_words.split(', ')
            self.targets = random.sample(team_words, min(2, len(team_words)))
        self.number_of_targets = len(self.targets)
        self.clue = "".join(random.sample(list(string.ascii_lowercase), 6))
        return self.recover_utterance(with_targets=True)

    def check_morphological_similarity(self, utterance, clue, remaining_words):
        clue_lemma = EN_LEMMATIZER.lemmatize(clue)
        remaining_word_lemmas = [EN_LEMMATIZER.lemmatize(word) for word in remaining_words]
        print(clue_lemma)
        print(remaining_word_lemmas)
        if clue_lemma in remaining_word_lemmas:
            similar_board_word = remaining_words[remaining_word_lemmas.index(clue_lemma)]
            raise RelatedClueError(utterance, clue, similar_board_word)
    
    def validate_response(self, utterance: str, remaining_words: List[str]):
        # utterance should contain two lines, one with the clue, one with the targets
        parts = utterance.split('\n')
        if len(parts) < 1:
            raise TooFewTextError(utterance)
        elif len(parts) > 2:
            if not self.flags["IGNORE RAMBLING"]:
                raise CluegiverRamblingError(utterance)
            else:
                self.flags_engaged["IGNORE RAMBLING"] += 1

        clue = find_line_starting_with(self.clue_prefix, parts)
        targets = find_line_starting_with(self.target_prefix, parts)
        if not clue:
            raise MissingCluePrefix(utterance, self.clue_prefix)
        if not targets:
            raise MissingTargetPrefix(utterance, self.target_prefix)
        
        clue = clue.removeprefix(self.clue_prefix).lower()
        if any(character in clue for character in CHARS_TO_STRIP):
            if self.flags["STRIP WORDS"]:
                self.flags_engaged["STRIP WORDS"] += 1
                clue = clue.strip(CHARS_TO_STRIP)
            else:
                raise ClueContainsNonAlphabeticalCharacters(utterance, clue)
        if re.search(r", [0-9]+", clue):
            if self.flags["IGNORE NUMBER OF TARGETS"]:
                self.flags_engaged["IGNORE NUMBER OF TARGETS"] += 1
                clue  = clue.strip(NUMBERS_TO_STRIP)
            else:
                raise ClueContainsNumberOfTargets(utterance, clue)

        targets = targets.removeprefix(self.target_prefix).split(', ')
        for target in targets:
            if any(character in target for character in CHARS_TO_STRIP):
                if self.flags["STRIP WORDS"]:
                    self.flags_engaged["STRIP WORDS"] += 1
        if self.flags["STRIP WORDS"]:
            targets = [target.strip(CHARS_TO_STRIP) for target in targets]
        targets = [target.lower() for target in targets]
        
        # Clue needs to be a single word
        if ' ' in clue:
            raise ClueContainsSpaces(utterance, clue)
        if not clue.isalpha():
            raise ClueContainsNonAlphabeticalCharacters(utterance, clue)
        # Clue needs to contain a word that is not morphologically similar to any word on the board
        self.check_morphological_similarity(utterance, clue, remaining_words)
        if clue in remaining_words:
            raise ClueOnBoardError(utterance, clue, remaining_words)
        
        for target in targets:
            if not target in remaining_words:
                if self.flags["IGNORE FALSE TARGETS OR GUESSES"]:
                    self.flags_engaged["IGNORE FALSE TARGETS OR GUESSES"] += 1
                else:
                    raise InvalidTargetError(utterance, target, remaining_words)
            
    def parse_response(self, utterance: str) -> str:
        parts = utterance.split('\n')
        clue = find_line_starting_with(self.clue_prefix, parts).removeprefix(self.clue_prefix)
        targets = find_line_starting_with(self.target_prefix, parts).removeprefix(self.target_prefix)
        self.clue = clue.lower().strip(CHARS_TO_STRIP).strip(NUMBERS_TO_STRIP)
        self.targets = targets.split(', ')
        self.targets = [target.strip(CHARS_TO_STRIP).lower() for target in self.targets]
        self.number_of_targets = len(self.targets)
        return self.recover_utterance()

    def recover_utterance(self) -> str:
        targets = ', '.join(self.targets)
        return f"{self.clue_prefix}{self.clue}\n{self.target_prefix}{targets}"


class Guesser(Player):
    def __init__(self, model_name: str, flags: Dict[str, bool]):
        super().__init__(model_name)
        self.guesses: List[str] = ['guess', 'word']
        self.prefix: str = "GUESS: "
        self.retries: int = 0
        self.flags = flags
        self.flags_engaged = {key: 0 for key, value in flags.items()}

    def _custom_response(self, history, turn) -> str:
        prompt = history[-1]["content"]
        board = prompt.split('\n\n')[1].split(', ')
        number_of_allowed_guesses = int(re.search(r"up to ([0-9]+) words", prompt).group(1))
        self.guesses = random.sample(board, number_of_allowed_guesses)
        self.guesses = [word.strip('. ') for word in self.guesses]
        return self.recover_utterance()
    
    def validate_response(self, utterance: str, remaining_words: List[str], number_of_allowed_guesses: int):
        # utterance should only contain one line
        if '\n' in utterance:
            if self.flags["IGNORE RAMBLING"]:
                line = find_line_starting_with(self.prefix, utterance.split('\n'))
                self.flags_engaged["IGNORE RAMBLING"] += 1
                if line:
                    utterance = line
            else:
                raise GuesserRamblingError(utterance)
        # utterance needs to start with GUESS
        if not utterance.startswith(self.prefix):
            raise MissingGuessPrefix(utterance, self.prefix)
        utterance = utterance.removeprefix(self.prefix)
        
        guesses = utterance.split(', ')
        for guess in guesses:
            if any(character in guess for character in CHARS_TO_STRIP):
                if self.flags["STRIP WORDS"]:
                    self.flags_engaged["STRIP WORDS"] += 1
                else:
                    raise GuessContainsInvalidCharacters(utterance, guess)
        if self.flags["STRIP WORDS"]:
            guesses = [word.strip(CHARS_TO_STRIP) for word in guesses]
        guesses = [guess.lower() for guess in guesses]
        # must contain one valid guess, but can only contain $number guesses max
        if not (0 < len(guesses) <= number_of_allowed_guesses):
            raise WrongNumberOfGuessesError(utterance, guesses, number_of_allowed_guesses)
        # guesses must be words on the board that are not revealed yet
        for guess in guesses:
            if not guess in remaining_words:
                if self.flags["IGNORE FALSE TARGETS OR GUESSES"]:
                    self.flags_engaged["IGNORE FALSE TARGETS OR GUESSES"] += 1
                else:
                    raise InvalidGuessError(utterance, guess, remaining_words)
            
    def parse_response(self, utterance: str) -> str:
        if self.flags["IGNORE RAMBLING"]:
            utterance = find_line_starting_with(self.prefix, utterance.split('\n'))
        utterance = utterance.removeprefix(self.prefix)
        self.guesses = utterance.split(', ')
        self.guesses = [word.strip(CHARS_TO_STRIP).lower() for word in self.guesses]
        return self.recover_utterance()
            
    def recover_utterance(self) -> str:
        return f"{self.prefix}{', '.join(self.guesses)}"