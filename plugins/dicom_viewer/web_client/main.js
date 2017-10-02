import _ from 'underscore';

import { getCurrentUser } from 'girder/auth';
import { AccessType } from 'girder/constants';
import events from 'girder/events';
import { restRequest } from 'girder/rest';
import { wrap } from 'girder/utilities/PluginUtils';
import ItemView from 'girder/views/body/ItemView';

import DicomView from './views/DicomView';
import parseDicomItemTemplate from './templates/parseDicomItem.pug';

wrap(ItemView, 'render', function (render) {
    this.once('g:rendered', function () {
        if (this.model.get('_accessLevel') >= AccessType.WRITE) {
            this.$('.g-item-actions-menu').prepend(parseDicomItemTemplate({
                item: this.model,
                currentUser: getCurrentUser()
            }));
        }
        this.$('.g-item-header').after('<div class="g-dicom-view"></div>');
        const view = new DicomView({
            el: this.$('.g-dicom-view'),
            parentView: this,
            item: this.model
        });
        view.render();
    }, this);
    return render.call(this);
});

ItemView.prototype.events['click .g-dicom-parse-item'] = function () {
    restRequest({
        method: 'POST',
        url: `item/${this.model.id}/parseDicom`
    }).done(_.bind(function (resp) {
        // Show up a message to alert the user it was done
        let text;
        let icon;
        let type;
        if (resp === null) {
            icon = 'cancel';
            text = 'No Dicom metadata.';
            type = 'danger';
        } else {
            icon = 'ok';
            text = 'Dicom item parsed.';
            type = 'success';
        }
        events.trigger('g:alert', {
            icon: icon,
            text: text,
            type: type,
            timeout: 4000
        });
    }, this));
};
