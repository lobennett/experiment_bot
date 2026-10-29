import Foundation
import Vision
import ImageIO

// Offline generic OCR configuration comparison; images are read-only.
// Arguments: image paths. Runs full image and an externally supplied optional
// crop (environment OCR_CROP=x,y,width,height, source pixels, top-left).
let cropValues = ProcessInfo.processInfo.environment["OCR_CROP"]?.split(separator: ",").compactMap { Int($0) }
for path in CommandLine.arguments.dropFirst() {
    let url = URL(fileURLWithPath: path)
    guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
          let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else { fatalError("image decode failed") }
    var regions = [CGRect(x: 0, y: 0, width: image.width, height: image.height)]
    if let c = cropValues, c.count == 4 {
        regions.append(CGRect(x: c[0], y: c[1], width: c[2], height: c[3]))
    }
    for region in regions {
        guard let input = image.cropping(to: region) else { fatalError("invalid crop") }
        for revision in VNRecognizeTextRequest.supportedRevisions {
            for accurate in [true, false] {
                for correction in [false, true] {
                    let started = Date()
                    let request = VNRecognizeTextRequest()
                    request.revision = revision
                    request.recognitionLevel = accurate ? .accurate : .fast
                    request.recognitionLanguages = ["en-US"]
                    request.usesLanguageCorrection = correction
                    request.minimumTextHeight = 0
                    var result: [String: Any] = [
                        "path": path, "image_width": image.width, "image_height": image.height,
                        "region": [region.minX, region.minY, region.width, region.height],
                        "revision": revision, "level": accurate ? "accurate" : "fast", "correction": correction
                    ]
                    do {
                        try VNImageRequestHandler(cgImage: input, options: [:]).perform([request])
                        result["observations"] = (request.results ?? []).map { item in
                            return ["candidates": item.topCandidates(5).map {
                                ["text": $0.string, "confidence": $0.confidence]
                            }]
                        }
                    } catch { result["error"] = String(describing: error) }
                    result["seconds"] = Date().timeIntervalSince(started)
                    let data = try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
                    print(String(decoding: data, as: UTF8.self))
                    fflush(stdout)
                }
            }
        }
    }
}
