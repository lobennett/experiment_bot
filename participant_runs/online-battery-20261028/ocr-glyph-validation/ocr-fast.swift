// macOS only. Compile into a run directory or /tmp:
// swiftc ocr.swift -o /tmp/participant-ocr
// /tmp/participant-ocr screenshot.png [--crop x y width height]
// Crop coordinates and returned boxes use source-image pixels, top-left origin.
// The input image is read only; no images or files are written by this helper.
import Foundation
import Vision
import ImageIO

struct OCRFailure: Error, CustomStringConvertible {
    let description: String
    init(_ description: String) { self.description = description }
}

func run() throws {
    let args = CommandLine.arguments
    let usage = "Usage: \(args[0]) image-path [--crop x y width height]"
    if args.count == 2 && ["--help", "-h"].contains(args[1]) {
        print(usage)
        return
    }
    guard args.count == 2 || (args.count == 7 && args[2] == "--crop") else {
        throw OCRFailure(usage)
    }
    let url = URL(fileURLWithPath: args[1]).standardizedFileURL
    guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
          let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
        throw OCRFailure("Cannot decode image: \(url.path)")
    }
    // Screenshots are already oriented. Reject an encoded rotation rather than
    // reporting source-pixel boxes against a silently rotated representation.
    if let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
       let orientation = properties[kCGImagePropertyOrientation] as? NSNumber,
       orientation.intValue != 1 {
        throw OCRFailure("Image orientation must be 1; supply an upright screenshot.")
    }
    var x = 0, y = 0, width = image.width, height = image.height
    if args.count == 7 {
        guard let cropX = Int(args[3]), let cropY = Int(args[4]),
              let cropWidth = Int(args[5]), let cropHeight = Int(args[6]),
              cropX >= 0, cropY >= 0, cropWidth > 0, cropHeight > 0,
              cropX < image.width, cropY < image.height,
              cropWidth <= image.width - cropX,
              cropHeight <= image.height - cropY else {
            throw OCRFailure("Crop must be positive integer dimensions inside the source image.")
        }
        x = cropX; y = cropY; width = cropWidth; height = cropHeight
    }
    let region = CGRect(x: x, y: y, width: width, height: height)
    guard let input = image.cropping(to: region) else {
        throw OCRFailure("Unable to read the requested image region.")
    }
    let request = VNRecognizeTextRequest()
    request.revision = 3
    request.recognitionLevel = .fast
    request.recognitionLanguages = ["en-US"]
    request.minimumTextHeight = 0
    request.usesLanguageCorrection = false
    try VNImageRequestHandler(cgImage: input, options: [:]).perform([request])
    let observations: [[String: Any]] = (request.results ?? []).compactMap { item in
        let candidates = item.topCandidates(3)
        guard let candidate = candidates.first else { return nil }
        let box = item.boundingBox
        return [
            "text": candidate.string,
            "confidence": candidate.confidence,
            "candidates": candidates.map { ["text": $0.string, "confidence": $0.confidence] },
            "box": [
                "x": Double(x) + box.minX * Double(width),
                "y": Double(y) + (1 - box.maxY) * Double(height),
                "width": box.width * Double(width),
                "height": box.height * Double(height)
            ]
        ]
    }
    let output: [String: Any] = [
        "image": ["path": url.path, "width": image.width, "height": image.height],
        "region": ["x": x, "y": y, "width": width, "height": height],
        "coordinate_system": "source_pixels_top_left",
        "text": observations.compactMap { $0["text"] as? String }.joined(separator: "\n"),
        "observations": observations
    ]
    let data = try JSONSerialization.data(withJSONObject: output, options: [.sortedKeys])
    print(String(decoding: data, as: UTF8.self))
}

do {
    try run()
} catch {
    FileHandle.standardError.write(Data("OCR error: \(error)\n".utf8))
    exit(1)
}
