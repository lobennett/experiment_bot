import re


class Participant:
    def __init__(self, seed=None):
        self.last_acted_frame = None
        self.words = []

    def respond(self, observation):
        text = ' '.join(observation['text'].split())
        lowered = text.lower()
        frame = observation['frame_id']
        if 'show data' in lowered and 'copy data' in lowered:
            return {'kind': 'done'}
        if not text or ('well done' in lowered and 'wait' in lowered):
            return {'kind': 'wait'}
        if frame == self.last_acted_frame:
            return {'kind': 'wait'}
        if 'self-paced reading task' in lowered and 'press space' in lowered:
            key = 'Space'
        elif 'press the n key' in lowered and 'following words' in lowered:
            key = 'n'
        elif re.fullmatch(r"[A-Za-z]+(?:['’-][A-Za-z]+)*[.,!?;:]?", text):
            self.words.append(text)
            key = 'n'
        else:
            return {'kind': 'unknown', 'text': text}
        self.last_acted_frame = frame
        return {'kind': 'key', 'key': key, 'timing': 'after_current_observation'}


def make_participant(seed=None):
    return Participant(seed)
