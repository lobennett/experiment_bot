function createParticipant(seed) {
  const answered = new Set();
  return {
    decide(observation) {
      const stimulus = observation.stimulus;
      if (!stimulus || !stimulus.rectangles.length || answered.has(stimulus.presentation)) return null;
      const present = stimulus.rectangles.some(rectangle => {
        const channels = rectangle.color.match(/[\d.]+/g)?.slice(0, 3).map(Number);
        return channels && channels.length === 3 && channels.every(c => c === 255) && rectangle.height > rectangle.width;
      });
      answered.add(stimulus.presentation);
      return {key: present ? '.' : ',', delay_ms: 0, presentation: stimulus.presentation};
    }
  };
}
if (typeof module !== 'undefined') module.exports = {createParticipant};
