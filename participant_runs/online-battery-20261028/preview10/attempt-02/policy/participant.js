function createParticipant(seed) {
  const answered = new Set();
  return {
    decide(observation) {
      const stimulus = observation.stimulus;
      if (!stimulus || answered.has(stimulus.presentation)) return null;
      const channels = stimulus.color.match(/[\d.]+/g)?.slice(0, 3).map(Number);
      if (!channels || channels.length !== 3 || channels.some(x => !Number.isFinite(x))) return null;
      const [red, green, blue] = channels;
      let key = null;
      if (red > green && red > blue) key = ',';
      if (blue > red && blue > green) key = '.';
      if (green > red && green > blue) key = '/';
      if (key === null) return null;
      answered.add(stimulus.presentation);
      return {key, presentation: stimulus.presentation};
    }
  };
}
if (typeof module !== 'undefined') module.exports = {createParticipant};
