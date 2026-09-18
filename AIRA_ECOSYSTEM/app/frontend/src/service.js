// app/src/services/location.js

export async function requestLocation(sessionId) {
    if (!("geolocation" in navigator)) {
        throw new Error("Browser tidak mendukung geolocation.");
    }

    return new Promise((resolve, reject) => {
        navigator.geolocation.getCurrentPosition(
            async (position) => {
                const coords = position.coords;

                const payload = {
                    session_id: sessionId,

                    latitude: coords.latitude,
                    longitude: coords.longitude,

                    accuracy: coords.accuracy,
                    altitude: coords.altitude,
                    heading: coords.heading,
                    speed: coords.speed,

                    permission: "granted",
                    source: "browser",

                    timestamp: Date.now() / 1000,
                };

                try {
                    const response = await fetch(
                        "/api/location",
                        {
                            method: "POST",
                            headers: {
                                "Content-Type": "application/json",
                            },
                            body: JSON.stringify(payload),
                        }
                    );

                    if (!response.ok) {
                        throw new Error(
                            `Location API error: ${response.status}`
                        );
                    }

                    const result = await response.json();

                    resolve(result);
                } catch (error) {
                    reject(error);
                }
            },

            (error) => {
                reject(error);
            },

            {
                enableHighAccuracy: true,
                timeout: 10000,
                maximumAge: 30000,
            }
        );
    });
}