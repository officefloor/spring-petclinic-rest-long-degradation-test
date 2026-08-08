package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** email-blocklist: Reject with 400 when the owner's email domain is on a disposable-domain blocklist (mailina... */
@Tag("cp38")
class Cp38Tests extends AcceptanceBase {

	@Test
	void errorRejectsDisposableDomain() throws Exception {
		ObjectNode o = ownerNode();
		o.put("email", "x@mailinator.com");
		createOwner(o).andExpect(status().isBadRequest());
	}
}
