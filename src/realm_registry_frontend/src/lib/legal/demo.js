import { LEGAL_CONTACT_EMAIL } from './legal-info.js';

/**
 * What the demo portal (and staging, which shares its data) adds to the Privacy Policy and the Terms of Use. The
 * demo is browse-only: registration codes are not published, so a visitor can write nothing others see. The texts
 * are the CLFO's (.ceo/clfo/launch/demo-environment.md, 27 Nov 2026); publishing codes needs them rewritten first.
 */

/** When the demo's additions last changed: a demo page shows this date, production keeps its own. */
const DEMO_LAST_UPDATED = '2026-11-27';

const SUBNET_COUNTRIES = {
  en: 'Belgium, Canada, Georgia, Hong Kong, India, the Isle of Man, Israel, Japan, Lithuania, Singapore, Slovenia, South Africa, South Korea, Sweden, Switzerland and the USA',
  es: 'Bélgica, Canadá, Corea del Sur, Eslovenia, Estados Unidos, Georgia, Hong Kong, India, la Isla de Man, Israel, Japón, Lituania, Singapur, Sudáfrica, Suecia y Suiza',
};

const DEMO_PRIVACY_SECTION = {
  en: {
    heading: '7. Demo environment',
    paragraphs: [
      'demo.gos.earth, demo.realmsgos.org and the realms reached from them are a public demo. Anyone can sign in with Internet Identity and look around, without an invitation. The cities, people, proposals and amounts in it are simulated.',
      'When you sign in, we process your Internet Identity principal. In the demo you can browse the realms and ask the AI assistant. You cannot post anything that other visitors see. Your conversations with the assistant are private to you and are kept as described in section 2. We use this data only to run the demo. Legal basis: providing the service you asked for (GDPR Art. 6(1)(b)). Please do not enter real personal data, yours or anyone else\'s.',
      'We reset the demo at least once every three months and when it closes. Copies on the Internet Computer may remain, as described in section 3.',
      'Services your browser contacts directly in the demo. They see your IP address, and some see more: Internet Identity and the Internet Computer\'s gateways (icp0.io, icp-api.io); Google Fonts (Google, USA); unpkg.com, for the code of the editor, maps and PDFs; map tiles from OpenStreetMap (United Kingdom) and OpenFreeMap (Hungary); the Internet Computer dashboard API, for node locations; GitHub (USA), for documents and the codex; DiceBear (Germany), for avatar images. It receives your principal as the seed.',
      'The assistant sends your questions, your principal and the realm you are in to our assistant service through Cloudflare (USA), and an AI model of Infomaniak AI Services (Switzerland) writes the answers.',
      `The demo runs on Internet Computer subnets whose nodes are in ${SUBNET_COUNTRIES.en}. Some of these states have no adequate data protection under Swiss law or the GDPR, and no contractual safeguards cover the node providers. Your data goes there only because it is directly needed to provide the demo you asked for (FADP Art. 17(1)(b); GDPR Art. 49(1)(b)). This is one more reason not to enter real personal data.`,
      'The technical logs of the demo\'s canisters can be read by anyone. They may contain principals and the text of error messages, including your principal when an operation on your record fails.',
    ],
  },
  es: {
    heading: '7. Entorno de demostración',
    paragraphs: [
      'demo.gos.earth, demo.realmsgos.org y los realms a los que se accede desde ellos son una demo pública. Cualquiera puede iniciar sesión con Internet Identity y echar un vistazo, sin invitación. Las ciudades, personas, propuestas e importes son simulados.',
      'Cuando inicias sesión, tratamos tu principal de Internet Identity. En la demo puedes recorrer los realms y preguntar al asistente de IA. No puedes publicar nada que vean otros visitantes. Tus conversaciones con el asistente son privadas y se conservan como se explica en la sección 2. Usamos estos datos solo para hacer funcionar la demo. Base jurídica: prestar el servicio que has pedido (art. 6(1)(b) RGPD). Por favor, no introduzcas datos personales reales, ni tuyos ni de otras personas.',
      'Reiniciamos la demo al menos una vez cada tres meses y cuando se cierre. Pueden quedar copias en Internet Computer, como se explica en la sección 3.',
      'Servicios a los que tu navegador se conecta directamente en la demo. Ven tu dirección IP, y algunos ven más: Internet Identity y las pasarelas de Internet Computer (icp0.io, icp-api.io); Google Fonts (Google, EE. UU.); unpkg.com, para el código del editor, los mapas y los PDF; teselas de mapa de OpenStreetMap (Reino Unido) y OpenFreeMap (Hungría); la API del panel de Internet Computer, para la ubicación de los nodos; GitHub (EE. UU.), para documentos y el códice; DiceBear (Alemania), para las imágenes de avatar. Recibe tu principal como semilla.',
      'El asistente envía tus preguntas, tu principal y el realm en el que estás a nuestro servicio de asistente a través de Cloudflare (EE. UU.), y un modelo de IA de Infomaniak AI Services (Suiza) escribe las respuestas.',
      `La demo funciona en subredes de Internet Computer cuyos nodos están en ${SUBNET_COUNTRIES.es}. Algunos de estos Estados no tienen una protección de datos adecuada según el derecho suizo o el RGPD, y ninguna garantía contractual cubre a los proveedores de nodos. Tus datos van allí solo porque es directamente necesario para prestarte la demo que has pedido (art. 17(1)(b) de la ley suiza de protección de datos; art. 49(1)(b) RGPD). Es un motivo más para no introducir datos personales reales.`,
      'Los registros técnicos (logs) de los canisters de la demo son legibles por cualquiera. Pueden contener principals y el texto de mensajes de error, incluido tu principal cuando falla una operación sobre tus datos.',
    ],
  },
};

const DEMO_TERMS_ADDENDUM = {
  en: {
    heading: 'Public demo',
    paragraphs: [
      `This is a public demo with simulated data. Anyone may sign in with Internet Identity; no invitation is needed. Nothing in it is an offer, a payment, or a decision of any real city or institution. EUR amounts and tokens have no value and cannot be paid out. We reset the demo at least once every three months and when it closes, and may close it at any time. Do not post illegal content or real personal data. We may remove any content and block any principal. Report content to ${LEGAL_CONTACT_EMAIL}. You must be at least 16. Otherwise the terms below apply.`,
    ],
  },
  es: {
    heading: 'Demo pública',
    paragraphs: [
      `Esta es una demo pública con datos simulados. Cualquiera puede iniciar sesión con Internet Identity; no hace falta invitación. Nada de lo que contiene es una oferta, un pago ni una decisión de ninguna ciudad o institución real. Los importes en EUR y los tokens no tienen valor y no se pueden cobrar. Reiniciamos la demo al menos una vez cada tres meses y cuando se cierre, y podemos cerrarla en cualquier momento. No publiques contenido ilegal ni datos personales reales. Podemos retirar cualquier contenido y bloquear cualquier principal. Denuncia contenido en ${LEGAL_CONTACT_EMAIL}. Debes tener al menos 16 años. En lo demás se aplican las condiciones siguientes.`,
    ],
  },
};

// The sentence of the terms the demo addendum replaces: on the demo, access is not by invitation.
const BY_INVITATION = { en: 'Access is by invitation. ', es: 'El acceso es por invitación. ' };

/** The Privacy Policy with the demo's section after the others. */
export function demoPrivacy(privacy) {
  return mapLocales(privacy, (text, locale) => ({
    ...text,
    lastUpdated: DEMO_LAST_UPDATED,
    sections: [...text.sections, DEMO_PRIVACY_SECTION[locale] ?? DEMO_PRIVACY_SECTION.en],
  }));
}

/** The Terms of Use with the demo addendum first, and without the sentence it replaces. */
export function demoTerms(terms) {
  return mapLocales(terms, (text, locale) => ({
    ...text,
    lastUpdated: DEMO_LAST_UPDATED,
    sections: [
      DEMO_TERMS_ADDENDUM[locale] ?? DEMO_TERMS_ADDENDUM.en,
      ...text.sections.map((section) => ({
        ...section,
        paragraphs: section.paragraphs.map((paragraph) => paragraph.replace(BY_INVITATION[locale] ?? BY_INVITATION.en, '')),
      })),
    ],
  }));
}

function mapLocales(texts, change) {
  return Object.fromEntries(Object.entries(texts).map(([locale, text]) => [locale, change(text, locale)]));
}
