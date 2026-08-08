package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** email-blocklist: the disposable-domain blocklist is still applied first, so a
 * blocklisted email is rejected with 400 before identity checks. */
@Tag("cp38")
class Cp38Tests extends AcceptanceBase {

	@Test
	void coreRejectsBlocklistedDomain() throws Exception {
		ObjectNode o = structuredOwner();
		o.put("email", "x@mailinator.com");
		createOwner(o).andExpect(status().isBadRequest());
	}
}
