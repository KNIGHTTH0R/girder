import $ from 'jquery';
import _ from 'underscore';

import View from 'girder/views/View';
import { restRequest } from 'girder/rest';
import router from 'girder/router';

import SearchResultsTemplate from 'girder/templates/body/searchResults.pug';

import 'girder/stylesheets/body/searchResultsList.styl';

import CollectionCollection from 'girder/collections/CollectionCollection';
import GroupCollection from 'girder/collections/GroupCollection';
import UserCollection from 'girder/collections/UserCollection';
import FolderCollection from 'girder/collections/FolderCollection';
import ItemCollection from 'girder/collections/ItemCollection';

import PaginateWidget from 'girder/views/widgets/PaginateWidget';

var SearchResultsView = View.extend({
    events: {
        'click .g-search-result>a': function (e) {
            this._resultClicked($(e.currentTarget));
        }
    },

    /**
     * This view display all the search results per each type
     */
    initialize: function (settings) {
        this.ajaxLock = false;
        this.pending = null;
        this.rawResults = [];
        this.results = [];
        this.paginationLimit = 6;
        this.query = settings.query;
        this.mode = settings.mode;
        this.types = settings.types || ['collection', 'group', 'user', 'folder', 'item'];

        const collectionPaginate = new PaginateWidget({
            parentView: this,
            collection: new CollectionCollection()
        });
        const groupPaginate = new PaginateWidget({
            parentView: this,
            collection: new GroupCollection()
        });
        const userPaginate = new PaginateWidget({
            parentView: this,
            collection: new UserCollection()
        });
        const folderPaginate = new PaginateWidget({
            parentView: this,
            collection: new FolderCollection()
        });
        const itemPaginate = new PaginateWidget({
            parentView: this,
            collection: new ItemCollection()
        });

        this.paginateWidgets = {
            'collection': collectionPaginate,
            'group': groupPaginate,
            'user': userPaginate,
            'folder': folderPaginate,
            'item': itemPaginate
        };

        this.search();
    },

    search: function () {
        if (!this.query) {
            this.render();
        }
        if (this.ajaxLock) {
            this.pending = this.query;
        } else {
            const rawPromise = this._doSearch(this.query);
            rawPromise.done(() => {
                if (this.rawResults.length !== 0) {
                    this.results = this._parse_result(this.rawResults);
                }
                this.render();
            });
        }
    },

    _resultClicked: function (result) {
        router.navigate(result.attr('resourcetype') + '/' + result.attr('resourceid'), {
            trigger: true
        });
    },

    render: function () {
        this.$el.html(SearchResultsTemplate({
            results: this.results || null,
            query: this.query || null,
            limit: this.paginationLimit
        }));
        // set paginateWidget only for results types containing elements
        this.results.forEach((result) => {
            for (var key in this.paginateWidgets) {
                if (result.type === key) {
                    this.paginateWidgets[key].setElement(this.$(`#${result.type}Paginate`)).render();
                }
            }
        });

        return this;
    },

    /**
     * This function has to convert the result object from the searchFieldWidget
     * to an object like :
     *      results = [{
     *          type: type,
     *          icon: icon_type,
     *          elements: [{
     *              id: obj_id,
     *              text: obj_name
     *          }, ...]
     *      }, ...]
     * which contain each results with the same type in the same list 'elements'.
     */
    _parse_result: function (rawResults) {
        var results = [];
        var collections = [];
        var folders = [];
        var items = [];
        var users = [];
        var groups = [];
        var elements = [];
        const icons = ['sitemap', 'users', 'user', 'folder', 'doc-text-inv'];
        rawResults.forEach((result) => {
            if (result.type === 'collection') {
                collections.push(result);
            } else if (result.type === 'group') {
                groups.push(result);
            } else if (result.type === 'user') {
                users.push(result);
            } else if (result.type === 'folder') {
                folders.push(result);
            } else if (result.type === 'item') {
                items.push(result);
            } else {
                console.log('Error type: ' + result.type + 'inconnu');
            }
        });
        var resultsTypes = [collections, groups, users, folders, items];
        for (var k = 0; k < resultsTypes.length; k++) {
            resultsTypes[k].forEach((element) => {
                elements.push({
                    id: element.id,
                    text: element.text
                });
            });
            if (elements.length !== 0) {
                results.push({
                    type: this.types[k],
                    icon: icons[k],
                    elements: elements
                });
            }
            elements = [];
        }
        return results;
    },

    _doSearch: function (q) {
        this.ajaxLock = true;
        this.pending = null;

        const rawResultsPromise = restRequest({
            url: 'resource/search',
            data: {
                q: q,
                mode: this.mode,
                types: JSON.stringify(this.types)
            }
        }).done(_.bind(function (results) {
            this.ajaxLock = false;

            if (this.pending) {
                this._doSearch(this.pending);
            } else {
                var resources = [];
                _.each(this.types, function (type) {
                    _.each(results[type] || [], function (result) {
                        var text, icon;
                        if (type === 'user') {
                            text = result.firstName + ' ' + result.lastName +
                                ' (' + result.login + ')';
                            icon = 'user';
                        } else if (type === 'group') {
                            text = result.name;
                            icon = 'users';
                        } else if (type === 'collection') {
                            text = result.name;
                            icon = 'sitemap';
                        } else if (type === 'folder') {
                            text = result.name;
                            icon = 'folder';
                        } else if (type === 'item') {
                            text = result.name;
                            icon = 'doc-text-inv';
                        } else {
                            if (!text || !icon) {
                                text = '[unknown type]';
                                icon = 'attention';
                            }
                        }
                        resources.push({
                            type: type,
                            id: result._id,
                            text: text,
                            icon: icon
                        });
                    }, this);
                }, this);
                this.rawResults = resources;
            }
        }, this));
        return rawResultsPromise;
    }
});

export default SearchResultsView;
