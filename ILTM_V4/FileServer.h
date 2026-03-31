#include <WiFi.h>
#include <WebServer.h>
#include <SD.h>

class FileServer {
private:
    WebServer server(80);

    void handleFileList() {
        File root = SD.open("/");
        File file = root.openNextFile();

        String json = "[";

        while (file) {
            if (json.length() > 1) json += ",";
            json += "\"" + String(file.name()) + "\"";
            file = root.openNextFile();
        }

        json += "]";
        server.send(200, "application/json", json);
    }

    void handleDownload() {
        if (!server.hasArg("name")) {
            server.send(400, "text/plain", "Missing file name");
            return;
        }

        String filename = "/" + server.arg("name");
        File file = SD.open(filename);

        if (!file) {
            server.send(404, "text/plain", "File not found");
            return;
        }

        server.streamFile(file, "application/octet-stream");
        file.close();
    }

    void handleRoot() {
        String html = "<html><body><h2>Files</h2><ul>";

        File root = SD.open("/");
        File file = root.openNextFile();

        while (file) {
            String name = String(file.name());
            html += "<li><a href=\"/download?name=" + name + "\">" + name + "</a></li>";
            file = root.openNextFile();
        }

        html += "</ul></body></html>";

        server.send(200, "text/html", html);
    }

public:
    void begin() {
        server.on("/", handleRoot);
        server.on("/files", handleFileList);
        server.on("/download", handleDownload);

        server.begin();
    }
};