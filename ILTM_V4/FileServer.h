#pragma once
#include <WiFi.h>
#include <WebServer.h>
#include <SD.h>

class FileServer {
private:
    WebServer server;
    TaskHandle_t serverTaskHandle = nullptr;
    bool running = false;

    // ===== HANDLERS =====
    void handleFileList() {
        String dir = "/";

        if (server.hasArg("dir")) {
            dir = server.arg("dir");
        }

        File root = SD.open(dir);
        File file = root.openNextFile();

        String json = "[";

        while (file) {
            if (!file.isDirectory()) {
                if (json.length() > 1) json += ",";
                json += "\"" + String(file.name()) + "\"";
            }
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

        String filename = server.arg("name");   // includes extension
        String path = "/" + filename;

        File file = SD.open(path);
        if (!file) {
            server.send(404, "text/plain", "File not found");
            return;
        }

        // Force correct download name
        server.sendHeader("Content-Disposition", "attachment; filename=\"" + filename + "\"");

        server.streamFile(file, "application/octet-stream");
        file.close();
    }

    void handleRoot() {
        String dir = "/";

        if (server.hasArg("dir")) {
            dir = server.arg("dir");
        }

        File root = SD.open(dir);
        if (!root || !root.isDirectory()) {
            server.send(404, "text/plain", "Invalid directory");
            return;
        }

        String html = "<html><body>";
        html += "<h2>Directory: " + dir + "</h2><ul>";

        // Back button (unless root)
        if (dir != "/") {
            int lastSlash = dir.lastIndexOf('/');
            String parent = (lastSlash <= 0) ? "/" : dir.substring(0, lastSlash);
            html += "<li><a href=\"/?dir=" + parent + "\">[..]</a></li>";
        }

        File file = root.openNextFile();

        while (file) {
            String name = String(file.name());
            String fullPath = dir + (dir == "/" ? "" : "/") + name;

            if (file.isDirectory()) {
                html += "<li><b><a href=\"/?dir=" + fullPath + "\">[DIR] " + name + "</a></b></li>";
            } else {
                html += "<li><a href=\"/download?name=" + fullPath + "\">" + name + "</a></li>";
            }

            file = root.openNextFile();
        }

        html += "</ul></body></html>";

        server.send(200, "text/html", html);
    }

    // ===== TASK LOOP =====
    static void serverTask(void* param) {
        FileServer* self = static_cast<FileServer*>(param);

        while (self->running) {
            self->server.handleClient();
            vTaskDelay(10 / portTICK_PERIOD_MS); // don't hog CPU
        }

        vTaskDelete(NULL);
    }

public:
    FileServer() : server(80) {}

    void begin() {
        if (running) return;

        // Routes
        server.on("/", [this]() { handleRoot(); });
        server.on("/files", [this]() { handleFileList(); });
        server.on("/download", [this]() { handleDownload(); });

        server.begin();

        running = true;

        // Start task (core 1 is usually safer)
        xTaskCreatePinnedToCore(
            serverTask,
            "FileServerTask",
            4096,
            this,
            1,
            &serverTaskHandle,
            1
        );
    }

    void stop() {
        if (!running) return;

        running = false;

        // Give task time to exit
        vTaskDelay(50 / portTICK_PERIOD_MS);

        if (serverTaskHandle != nullptr) {
            vTaskDelete(serverTaskHandle);
            serverTaskHandle = nullptr;
        }

        server.stop(); // actually shuts down server
    }

    bool isRunning() {
        return running;
    }
};