import assert from 'node:assert/strict';
import test from 'node:test';
import {
	embeddedPathFromPortalPathname,
	portalHistoryHref,
	portalPath,
} from './federation-path.js';

test('embeddedPathFromPortalPathname strips /r/{slug}', () => {
	assert.equal(embeddedPathFromPortalPathname('/r/initargdemo', 'initargdemo'), '/');
	assert.equal(
		embeddedPathFromPortalPathname('/r/initargdemo/extensions/member_dashboard', 'initargdemo'),
		'/extensions/member_dashboard',
	);
	assert.equal(
		embeddedPathFromPortalPathname('/r/initargdemo/extensions/import_export', 'initargdemo'),
		'/extensions/import_export',
	);
});

test('portalHistoryHref keeps host ?ti= when the iframe path omitted it', () => {
	assert.equal(
		portalHistoryHref(
			'initargdemo',
			'/extensions/import_export',
			'https://demo.gos.earth/r/initargdemo/extensions/member_dashboard?ti=1',
		),
		'/r/initargdemo/extensions/import_export?ti=1',
	);
});

test('portalHistoryHref does not duplicate a path that already matches', () => {
	assert.equal(
		portalPath('initargdemo', '/extensions/member_dashboard'),
		'/r/initargdemo/extensions/member_dashboard',
	);
	assert.equal(
		portalHistoryHref(
			'initargdemo',
			'/extensions/member_dashboard',
			'https://demo.gos.earth/r/initargdemo/extensions/member_dashboard?ti=1',
		),
		'/r/initargdemo/extensions/member_dashboard?ti=1',
	);
});
