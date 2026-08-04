frappe.pages['geo-attendance'].on_page_load = function (
    wrapper
) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __('Geo Attendance'),
        single_column: true
    });

    const container = $(`
        <div class="geo-attendance-container"
             style="max-width: 620px; margin: 25px auto;">
            <div class="card">
                <div class="card-body">
                    <h4>${__('Worker Attendance')}</h4>

                    <div class="geo-context text-muted"
                         style="margin: 15px 0;">
                        ${__('Loading attendance information...')}
                    </div>

                    <button class="btn btn-primary btn-lg
                                   btn-record-attendance"
                            style="width: 100%;"
                            disabled>
                        ${__('Loading...')}
                    </button>

                    <div class="geo-result"
                         style="margin-top: 20px;">
                    </div>
                </div>
            </div>
        </div>
    `);

    $(page.body).append(container);

    const contextBox =
        container.find('.geo-context');

    const recordButton =
        container.find('.btn-record-attendance');

    const resultBox =
        container.find('.geo-result');

    let context = null;

    function loadContext() {
        recordButton.prop('disabled', true);

        frappe.call({
            method:
                'jari_core.geo_attendance.get_attendance_context',
            callback(r) {
                context = r.message;

                if (!context) {
                    return;
                }

                contextBox.html(`
                    <div>
                        <strong>${__('Worker')}:</strong>
                        ${frappe.utils.escape_html(
                            context.worker || ''
                        )}
                    </div>
                    <div>
                        <strong>${__('Location')}:</strong>
                        ${frappe.utils.escape_html(
                            context.location || ''
                        )}
                    </div>
                    <div>
                        <strong>${__('Allowed Radius')}:</strong>
                        ${flt(
                            context.allowed_radius_meters,
                            2
                        )} m
                    </div>
                `);

                recordButton
                    .text(
                        context.next_attendance_type === 'IN'
                            ? __('Check In')
                            : __('Check Out')
                    )
                    .prop('disabled', false);
            }
        });
    }

    recordButton.on('click', function () {
        if (!navigator.geolocation) {
            frappe.msgprint(
                __('Geolocation is not supported by this device.')
            );
            return;
        }

        recordButton
            .prop('disabled', true)
            .text(__('Capturing Location...'));

        navigator.geolocation.getCurrentPosition(
            position => {
                const coordinates =
                    position.coords;

                frappe.call({
                    method:
                        'jari_core.geo_attendance.record_attendance',
                    args: {
                        latitude:
                            coordinates.latitude,
                        longitude:
                            coordinates.longitude,
                        accuracy:
                            coordinates.accuracy,
                        device_information:
                            navigator.userAgent
                    },
                    freeze: true,
                    freeze_message:
                        __('Recording Attendance...'),
                    callback(r) {
                        const result = r.message;

                        if (!result) {
                            return;
                        }

                        resultBox.html(`
                            <div class="alert alert-success">
                                <strong>
                                    ${__(
                                        result.attendance_type
                                    )}
                                </strong>
                                ${__('recorded successfully.')}
                                <br>
                                ${__('Distance')}:
                                ${flt(
                                    result.distance_meters,
                                    2
                                )} m
                            </div>
                        `);

                        loadContext();
                    },
                    error() {
                        loadContext();
                    }
                });
            },
            error => {
                recordButton.prop(
                    'disabled',
                    false
                );

                recordButton.text(
                    context &&
                    context.next_attendance_type === 'OUT'
                        ? __('Check Out')
                        : __('Check In')
                );

                let message =
                    __('Unable to capture your location.');

                if (error.code === 1) {
                    message = __(
                        'Location permission was denied. '
                        + 'Enable location access and try again.'
                    );
                } else if (error.code === 2) {
                    message = __(
                        'Location information is unavailable.'
                    );
                } else if (error.code === 3) {
                    message = __(
                        'Location request timed out.'
                    );
                }

                frappe.msgprint(message);
            },
            {
                enableHighAccuracy: true,
                timeout: 20000,
                maximumAge: 0
            }
        );
    });

    loadContext();
};
