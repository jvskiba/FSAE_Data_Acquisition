#pragma once

#include <unordered_map>
#include <functional>
#include "ITV.h"

class CommandManager {
public:

    using Handler = std::function<void(const ITV::ITVMap&)>;

    void registerCommand(uint16_t cmd, Handler handler) {
        handlers[cmd] = handler;
    }

    void execute(uint16_t cmd, const ITV::ITVMap& data) {
        auto it = handlers.find(cmd);

        if (it != handlers.end()) {
            it->second(data);
        }
    }

private:
    std::unordered_map<uint16_t, Handler> handlers;
};